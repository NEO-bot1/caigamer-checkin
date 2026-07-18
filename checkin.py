import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from playwright.async_api import Page, async_playwright

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


def is_signin_complete(text: str) -> bool:
    """
    Determine whether the page already shows the sign-in success state.
    判断页面文案是否已经表示“今日已签到 / 已签到”。
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
    logger.info("Checking if login popup is already visible...")
    inputs = await page.query_selector_all("input")
    has_text_input = False
    has_password_input = False

    for inp in inputs:
        input_type = await inp.get_attribute("type")
        if input_type in ("text", "email"):
            has_text_input = True
        elif input_type == "password":
            has_password_input = True

    if has_text_input and has_password_input:
        logger.info("Login popup is already visible (auto-shown).")
        return

    logger.info("Login popup not auto-shown, clicking login link...")
    clicked = False
    for selector in LOGIN_SELECTORS:
        try:
            if await page.is_visible(selector, timeout=2000):
                await page.click(selector, timeout=5000)
                logger.info(f"Clicked login element: {selector}")
                clicked = True
                break
        except Exception as exc:
            logger.debug(f"Selector {selector} skipped: {exc}")

    if not clicked:
        logger.warning("No login button matched any known selector.")
        await take_screenshot(page, "02_login_popup_unmatched")

    await page.wait_for_selector("input[type='text'], input[type='email']", timeout=10000)


async def find_login_inputs(page: Page) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Return the username/email input and password input.
    找到页面中的账号输入框与密码输入框；这里优先识别通用输入类型。
    """
    inputs = await page.query_selector_all("input")
    username_input = None
    password_input = None

    for inp in inputs:
        input_type = await inp.get_attribute("type")
        if input_type in ("text", "email"):
            username_input = inp
        elif input_type == "password":
            password_input = inp

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

    logger.info("Filling username...")
    await username_input.fill(username)
    logger.info("Filling password...")
    await password_input.fill(password)
    await take_screenshot(page, "03_filled_form")

    logger.info("Submitting login form (pressing Enter)...")
    await password_input.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=10000)
    await take_screenshot(page, "04_after_login")


async def close_welcome_modal(page: Page) -> None:
    """
    Close the welcome modal if it appears after login.
    登录完成后，如果页面弹出欢迎弹窗，使用 JS 方式关闭并清理模态层。
    """
    logger.info("Checking for welcome modal popup...")
    modal_exists = await page.evaluate(
        """
        () => {
            return document.querySelector('.modal.show') !== null ||
                   document.querySelector('.modal[style*="display: block"]') !== null;
        }
        """
    )

    if not modal_exists:
        logger.info("No welcome modal found.")
        return

    logger.info("Welcome modal detected, closing it via JavaScript...")
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
    await page.wait_for_load_state("networkidle", timeout=10000)
    await take_screenshot(page, "04b_modal_closed")


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
    """
    sign_button = None
    for selector in SIGNIN_BUTTON_SELECTORS:
        try:
            sign_button = await page.wait_for_selector(selector, timeout=5000)
            logger.info(f"Found sign-in button with selector: {selector}")
            break
        except Exception as exc:
            logger.debug(f"Selector {selector} not found: {exc}")

    if sign_button:
        try:
            await retry_async(
                lambda: sign_button.click(timeout=5000),
                retries=1,
                delay_seconds=1,
                description="click sign-in button",
            )
            logger.info("Clicked sign-in button via Playwright")
            await page.wait_for_load_state("networkidle", timeout=10000)
            return "clicked-via-playwright"
        except Exception as exc:
            logger.warning(f"Playwright click failed: {exc}")

    clicked = await page.evaluate(
        """
        () => {
            var btn = document.querySelector('.tt_signpanel .btn.signBtn') ||
                      document.querySelector('.tt_signpanel .btn-primary');
            if (!btn) return 'button-not-found';

            btn.focus();
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));

            if (btn.onclick) btn.onclick();
            return 'clicked: ' + btn.tagName + (btn.id ? '#' + btn.id : '') +
                   (btn.className ? '.' + btn.className.split(' ').slice(0, 3).join('.') : '');
        }
        """
    )
    logger.info(f"JavaScript click result: {clicked}")
    await page.wait_for_load_state("networkidle", timeout=10000)
    return clicked


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
