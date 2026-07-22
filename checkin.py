import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from playwright.async_api import Page, async_playwright  # type: ignore[import-not-found]

# Base target URL / 目标站点地址
BASE_URL = "https://caigamer.cn/"

# Candidate selectors for login popup / 登录弹窗可能出现的选择器集合
LOGIN_SELECTORS = [
    "a[href*='login']",
    "a[href*='signin']",
    "[data-target*='login']",
    ".login-btn",
    "#login-btn",
    "a:has-text('登录')",
    "button:has-text('登录')",
    "a:has-text('Login')",
]
# Candidate sign-in button selectors / 签到按钮可能存在的选择器集合
SIGNIN_BUTTON_SELECTORS = [
    ".tt_signpanel .btn.signBtn",
    ".tt_signpanel .btn-primary",
]

# Sign-in status text node selector / 签到状态文字节点选择器
SIGNIN_TEXT_SELECTOR = "#sign_title"

# Markers that mean the user already checked in / 表示已签到的页面文案标记
CHECKIN_SUCCESS_MARKERS = ("今日已签到", "已签到")

# Simplified explicit XPaths provided by user (prefer these to heuristics)
USERNAME_XPATH = "/html/body/div[6]/div/div[2]/div[2]/form/div[1]/input"
PASSWORD_XPATH = "/html/body/div[6]/div/div[2]/div[2]/form/div[2]/input"
SIGNIN_BUTTON_XPATH = "/html/body/div[1]/div[1]/div[3]/div/main/section[2]/aside/div[2]/div[1]/div[2]/div"


def is_signin_complete(text: str) -> bool:
    """
    Determine whether the page already shows the sign-in success state.
    判断页面文案是否已经表示"今日已签到 / 已签到"。
    """
    return any(marker in text for marker in CHECKIN_SUCCESS_MARKERS)


@dataclass
class CheckinResult:
    """
    Structured result for automation pipelines.
    自动化任务返回的结构化结果，便于日志、CI 或后续扩展读取。
    """
    status: str
    message: str
    screenshot: Optional[str] = None
    api_response: Optional[Dict[str, Any]] = None

    def summary(self) -> str:
        """
        Produce a one-line summary string for logging.
        生成一行可直接写入日志的结果摘要，便于排查任务状态。
        """
        return (
            f"status={self.status}, message={self.message}, "
            f"screenshot={self.screenshot}, api_response={self.api_response}"
        )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("caigamer_checkin")


async def take_screenshot(page: Page, step_name: str) -> str:
    """
    Take a screenshot and save it with a timestamp.
    记录当前页面状态，便于定位登录、签到、异常等环节。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"page_{step_name}_{timestamp}.png"
    try:
        await page.screenshot(path=filename, full_page=True)
        logger.info(f"Screenshot saved: {filename}")
    except Exception as exc:
        logger.warning(f"Failed to save screenshot for {step_name}: {exc}")
    return filename


def get_credentials() -> Tuple[str, str]:
    """
    Read required credentials from environment variables.
    从环境变量读取用户名与密码；适配 GitHub Actions 或本地定时任务。
    """
    username = os.environ.get("CAIGAMER_USERNAME", "").strip()
    password = os.environ.get("CAIGAMER_PASSWORD", "").strip()
    return username, password


async def retry_async(
    operation: Callable[[], Awaitable[Any]],
    *,
    retries: int = 2,
    delay_seconds: float = 1.0,
    description: str = "operation",
) -> Any:
    """
    Run an async operation with short retries to improve resilience.
    对临时性失败的页面动作做短暂重试，降低因页面波动造成的误判。
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            logger.warning(f"{description} failed on attempt {attempt + 1}, retrying... ({exc})")
            await asyncio.sleep(delay_seconds)
    raise last_error


async def launch_browser(playwright: Any):
    """
    Launch Playwright Chromium with stable browser flags.
    使用无头 Chromium 启动浏览器，并设置中文/上海时区等环境参数。
    """
    logger.info("Launching Chromium browser...")
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--font-render-hinting=none",
            "--disable-font-subpixel-positioning",
            "--enable-font-antialiasing",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    page = await context.new_page()
    return browser, page


async def setup_response_listener(page: Page, signin_api_response: Dict[str, Any]) -> None:
    """
    Listen for network responses that look like sign-in APIs.
    监听网络返回，抓取可能与签到相关的 API 请求及响应内容。
    """

    async def handle_response(response):
        url = response.url
        if any(keyword in url.lower() for keyword in ("sign", "checkin", "qiandao")):
            logger.info(f"Sign-in API detected: {url}")
            try:
                body = await response.text()
                signin_api_response["last"] = {
                    "url": url,
                    "status": response.status,
                    "body": body[:500],
                }
                logger.info(f"Response status: {response.status}, body preview: {body[:200]}")
            except Exception as exc:
                logger.warning(f"Failed to read sign-in API response body: {exc}")

    page.on("response", handle_response)


async def open_homepage(page: Page) -> None:
    """
    Open the target site and wait for the main content to load.
    进入首页并等待主要内容与网络稳定下来，避免后续元素还没渲染完就开始点击。
    """
    logger.info(f"Navigating to {BASE_URL} ...")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_load_state("networkidle", timeout=10000)
    await take_screenshot(page, "01_homepage")


async def ensure_login_popup(page: Page) -> None:
    """
    Open the login popup if it is not already visible.
    先判断登录框是否已经自动弹出；如果没有，再尝试点击登录入口。
    """
    logger.info("Checking for login inputs using provided XPaths...")
    try:
        # Prefer explicit XPath; short timeout to avoid long stalls
        await page.wait_for_selector(f"xpath={USERNAME_XPATH}", timeout=3000)
        await page.wait_for_selector(f"xpath={PASSWORD_XPATH}", timeout=3000)
        logger.info("Login popup inputs found via XPath.")
        return
    except Exception:
        logger.info("XPath inputs not visible yet, attempting known login links...")

    # Fallback: try known login entry selectors
    for selector in LOGIN_SELECTORS:
        try:
            if await page.is_visible(selector, timeout=2000):
                await page.click(selector, timeout=5000)
                logger.info(f"Clicked login element: {selector}")
                break
        except Exception as exc:
            logger.debug(f"Selector {selector} skipped: {exc}")

    # Wait for username input to appear
    try:
        await page.wait_for_selector(f"xpath={USERNAME_XPATH}", timeout=10000)
    except Exception as exc:
        logger.warning(f"Username input not found after fallback: {exc}")
        await take_screenshot(page, "02_login_popup_unmatched")


async def find_login_inputs(page: Page) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Return the username/email input and password input.
    找到页面中的账号输入框与密码输入框；这里优先识别通用输入类型。
    """
    # Use explicit XPaths for robustness
    username_input = None
    password_input = None
    try:
        username_input = await page.wait_for_selector(f"xpath={USERNAME_XPATH}", timeout=5000)
    except Exception:
        username_input = None
    try:
        password_input = await page.wait_for_selector(f"xpath={PASSWORD_XPATH}", timeout=5000)
    except Exception:
        password_input = None
    return username_input, password_input


async def login(page: Page, username: str, password: str) -> None:
    """
    Fill in the username and password, then submit the login form.
    输入用户名密码并提交表单；若页面中有偶发性延迟，则通过重试提高稳健性。
    """
    username_input, password_input = await retry_async(
        lambda: find_login_inputs(page),
        retries=2,
        delay_seconds=1,
        description="locate login inputs",
    )

    if not username_input or not password_input:
        logger.error("Failed to locate username or password input field")
        await take_screenshot(page, "03_error_inputs")
        raise RuntimeError("login inputs were not found")

    logger.info("Filling username via XPath...")
    await username_input.fill(username)
    logger.info("Filling password via XPath...")
    await password_input.fill(password)
    await take_screenshot(page, "03_filled_form")

    logger.info("Submitting login form (pressing Enter)...")
    try:
        await password_input.press("Enter")
    except Exception:
        # Fallback: try to submit via form submit JS
        try:
            await page.evaluate("() => { var f = document.querySelector('form'); if(f) f.submit(); }")
            logger.info("Submitted login form via JS submit fallback")
        except Exception as exc:
            logger.warning(f"Failed to submit form via fallback: {exc}")

    # FIX: 等待页面导航完成，而不是立即检查弹窗
    logger.info("Waiting for page navigation after login...")
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as exc:
        logger.warning(f"wait_for_load_state networkidle timeout: {exc}")

    # 额外等待确保页面完全稳定
    await asyncio.sleep(3)
    await take_screenshot(page, "04_after_login")


async def close_welcome_modal(page: Page) -> None:
    """
    Close the welcome modal if it appears after login.
    登录完成后，如果页面弹出欢迎弹窗，使用 JS 方式关闭并清理模态层。
    FIX: 增加 try-except 捕获导航导致的执行上下文销毁错误。
    """
    logger.info("Checking for welcome modal popup...")

    # FIX: 先等待页面完全稳定，避免在导航过程中执行 JS
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception as exc:
        logger.warning(f"wait_for_load_state domcontentloaded timeout: {exc}")

    await asyncio.sleep(2)  # 额外等待让弹窗有时间出现

    modal_exists = False
    try:
        modal_exists = await page.evaluate(
            """
            () => {
                return document.querySelector('.modal.show') !== null ||
                       document.querySelector('.modal[style*="display: block"]') !== null ||
                       document.querySelector('.modal-backdrop') !== null;
            }
            """
        )
    except Exception as exc:
        logger.warning(f"Failed to evaluate modal existence (page may be navigating): {exc}")
        # FIX: 如果 evaluate 失败，尝试用选择器直接查找
        try:
            modal_el = await page.query_selector('.modal.show, .modal[style*="display: block"], .modal-backdrop')
            modal_exists = modal_el is not None
        except Exception as exc2:
            logger.warning(f"Query selector for modal also failed: {exc2}")
            modal_exists = False

    if not modal_exists:
        logger.info("No welcome modal found.")
        return

    logger.info("Welcome modal detected, closing it via JavaScript...")
    try:
        await page.evaluate(
            """
            () => {
                var modalEl = document.querySelector('.modal.show');
                if (modalEl && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                    var modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }
                document.querySelectorAll('.modal').forEach(m => {
                    m.classList.remove('show');
                    m.style.display = 'none';
                    m.setAttribute('aria-hidden', 'true');
                });
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }
            """
        )
        await asyncio.sleep(1)
        await take_screenshot(page, "04b_modal_closed")
    except Exception as exc:
        logger.warning(f"Failed to close modal via JavaScript: {exc}")
        # FIX: 如果 JS 关闭失败，尝试用键盘 ESC 关闭
        try:
            await page.keyboard.press("Escape")
            logger.info("Sent Escape key to close modal")
            await asyncio.sleep(1)
        except Exception as esc_exc:
            logger.warning(f"Escape key also failed: {esc_exc}")

    # FIX: 无论弹窗是否成功关闭，都等待页面稳定
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as exc:
        logger.warning(f"wait_for_load_state after modal close timeout: {exc}")
    await asyncio.sleep(2)


async def get_signin_text(page: Page) -> str:
    """
    Read the current sign-in status text from the page.
    读取页面上的签到状态文案，判断当前是否已经签到。
    """
    try:
        sign_text_el = await page.wait_for_selector(SIGNIN_TEXT_SELECTOR, timeout=5000)
        if sign_text_el:
            sign_text = await sign_text_el.inner_text()
            logger.info(f"Current sign-in text: '{sign_text}'")
            return sign_text
    except Exception as exc:
        logger.warning(f"Could not find sign-in text element: {exc}")
    return ""


async def click_signin_button(page: Page) -> str:
    """
    Click the sign-in button using Playwright first, then fallback to JavaScript.
    优先用 Playwright 原生点击；如果不可用，则退回到 JS 触发点击。
    FIX: 增加对遮罩层的处理，确保按钮可点击。
    """
    # FIX: 先移除可能的遮罩层和 modal-open 状态
    try:
        await page.evaluate(
            """
            () => {
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.querySelectorAll('.modal').forEach(m => {
                    m.classList.remove('show');
                    m.style.display = 'none';
                });
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }
            """
        )
        logger.info("Cleaned up potential overlay/modal-backdrop")
    except Exception as exc:
        logger.debug(f"Cleanup overlay failed (non-critical): {exc}")

    await asyncio.sleep(1)

    # Prefer explicit XPath for sign-in button
    try:
        sign_button = await page.wait_for_selector(f"xpath={SIGNIN_BUTTON_XPATH}", timeout=5000)
        await sign_button.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)
        await retry_async(lambda: sign_button.click(timeout=5000), retries=1, delay_seconds=1, description="click sign-in button")
        logger.info("Clicked sign-in button via XPath Playwright click")
        await page.wait_for_load_state("networkidle", timeout=10000)
        return "clicked-via-xpath"
    except Exception as exc:
        logger.warning(f"XPath sign-in click failed or not found: {exc}")

    # Fallback to previous selectors / JS click
    for selector in SIGNIN_BUTTON_SELECTORS:
        try:
            btn = await page.query_selector(selector)
            if btn:
                await btn.scroll_into_view_if_needed()
                await btn.click()
                logger.info(f"Clicked sign-in button with fallback selector: {selector}")
                await page.wait_for_load_state("networkidle", timeout=10000)
                return "clicked-via-fallback"
        except Exception as exc:
            logger.debug(f"Fallback selector click failed: {exc}")

    # Last resort: JS click by XPath
    try:
        clicked = await page.evaluate(f"() => {{ var el = document.evaluate('{SIGNIN_BUTTON_XPATH}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; if(!el) return 'button-not-found'; el.click(); return 'clicked-via-js-xpath'; }}")
        logger.info(f"JavaScript XPath click result: {clicked}")
        await page.wait_for_load_state("networkidle", timeout=10000)
        return clicked
    except Exception as exc:
        logger.warning(f"All click attempts failed: {exc}")
        return "click-failed"


async def verify_signin_result(page: Page, signin_api_response: Dict[str, Any]) -> bool:
    """
    Verify whether sign-in succeeded using page text and captured API response.
    通过页面文案与抓到的 API 响应共同判断签到是否真的成功。
    """
    sign_text_after = await get_signin_text(page)
    logger.info(f"Sign-in text after click: '{sign_text_after}'")

    if any(marker in sign_text_after for marker in CHECKIN_SUCCESS_MARKERS):
        logger.info("Sign-in completed successfully!")
        return True

    api_response = signin_api_response.get("last")
    if api_response and api_response.get("status") in (200, 201, 202):
        logger.info(f"API Response indicates sign-in was processed: {api_response}")
        return True

    logger.warning("Sign-in text does not indicate success. Checking API response...")
    if api_response:
        logger.info(f"API Response: {api_response}")
    return False


async def run_checkin() -> int:
    """
    Main check-in workflow.
    主流程：读取环境变量 -> 打开主页 -> 登录 -> 处理弹窗 -> 判断签到状态 -> 点击签到 -> 验证结果。
    """
    username, password = get_credentials()
    # Log presence of credentials without exposing values
    logger.info(
        "Credentials presence: username_present=%s, password_present=%s",
        bool(username),
        bool(password),
    )
    missing = []
    if not username:
        missing.append("CAIGAMER_USERNAME")
    if not password:
        missing.append("CAIGAMER_PASSWORD")
    if missing:
        logger.error("Missing environment variables: %s", ", ".join(missing))
        return 1

    result = CheckinResult(status="failed", message="check-in workflow did not complete")

    async with async_playwright() as playwright:
        browser = None
        page = None
        try:
            browser, page = await launch_browser(playwright)
            signin_api_response: Dict[str, Any] = {}
            await setup_response_listener(page, signin_api_response)

            await open_homepage(page)
            await ensure_login_popup(page)
            await take_screenshot(page, "02_login_popup")

            await login(page, username, password)

            # FIX: 登录后先等待页面完全稳定，再处理弹窗
            logger.info("Login submitted, waiting for page to stabilize...")
            await asyncio.sleep(3)

            await close_welcome_modal(page)

            logger.info("Checking sign-in status...")
            await page.wait_for_load_state("networkidle", timeout=10000)

            sign_text = await get_signin_text(page)
            if is_signin_complete(sign_text):
                logger.info("Already signed in today! No action needed.")
                result = CheckinResult(status="success", message="already signed in today")
                logger.info("Final result: %s", result.summary())
                return 0

            logger.info("Not signed in yet. Attempting to click sign-in button...")
            await click_signin_button(page)
            screenshot_path = await take_screenshot(page, "05_after_sign_click")
            result.screenshot = screenshot_path

            success = await verify_signin_result(page, signin_api_response)
            if success:
                logger.info("Check-in workflow completed successfully.")
                result = CheckinResult(
                    status="success",
                    message="check-in completed successfully",
                    screenshot=screenshot_path,
                    api_response=signin_api_response.get("last"),
                )
                logger.info("Final result: %s", result.summary())
                return 0

            logger.error("Check-in workflow completed, but the sign-in result could not be confirmed.")
            result = CheckinResult(
                status="failed",
                message="check-in could not be confirmed",
                screenshot=screenshot_path,
                api_response=signin_api_response.get("last"),
            )
            logger.info("Final result: %s", result.summary())
            return 1
        except Exception as exc:
            logger.exception(f"Unexpected error during check-in: {exc}")
            if page is not None:
                result.screenshot = await take_screenshot(page, "error")
            result.message = f"unexpected error: {exc}"
            logger.info("Final result: %s", result.summary())
            return 1
        finally:
            if browser is not None:
                logger.info("Closing browser...")
                await browser.close()


if __name__ == "__main__":
    exit_code = asyncio.run(run_checkin())
    sys.exit(exit_code)
