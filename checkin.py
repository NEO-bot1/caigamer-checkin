import asyncio
import os
import sys
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("caigamer_checkin")

async def take_screenshot(page, step_name):
    """Take a screenshot and save with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"page_{step_name}_{timestamp}.png"
    await page.screenshot(path=filename, full_page=True)
    logger.info(f"Screenshot saved: {filename}")
    return filename

async def run_checkin():
    """Main check-in workflow."""
    username = os.environ.get("CAIGAMER_USERNAME")
    password = os.environ.get("CAIGAMER_PASSWORD")

    if not username or not password:
        logger.error("Missing environment variables: CAIGAMER_USERNAME and/or CAIGAMER_PASSWORD")
        return 1

    async with async_playwright() as p:
        browser = None
        try:
            logger.info("Launching Chromium browser...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--font-render-hinting=none",
                    "--disable-font-subpixel-positioning",
                    "--enable-font-antialiasing"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai"
            )
            page = await context.new_page()

            # 监听网络请求，捕获签到 API
            signin_api_response = {}
            async def handle_response(response):
                url = response.url
                if 'sign' in url.lower() or 'checkin' in url.lower() or 'qiandao' in url.lower():
                    logger.info(f"Sign-in API detected: {url}")
                    try:
                        body = await response.text()
                        signin_api_response['last'] = {'url': url, 'status': response.status, 'body': body[:500]}
                        logger.info(f"Response status: {response.status}, body preview: {body[:200]}")
                    except:
                        pass
            page.on("response", handle_response)

            # Step 1: Navigate to homepage
            logger.info("Navigating to https://caigamer.cn/ ...")
            await page.goto("https://caigamer.cn/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            await take_screenshot(page, "01_homepage")

            # Step 2: Login popup may auto-show on page load; handle both cases
            logger.info("Checking if login popup is already visible...")
            all_inputs = await page.query_selector_all("input")
            has_text_input = False
            has_password_input = False
            for inp in all_inputs:
                input_type = await inp.get_attribute("type")
                if input_type in ("text", "email"):
                    has_text_input = True
                elif input_type == "password":
                    has_password_input = True

            if has_text_input and has_password_input:
                logger.info("Login popup is already visible (auto-shown).")
            else:
                logger.info("Login popup not auto-shown, clicking login link...")
                try:
                    # 尝试多种可能的登录按钮选择器
                    login_selectors = [
                        "a[href*='login']",
                        "a[href*='signin']",
                        "[data-target*='login']",
                        ".login-btn",
                        "#login-btn",
                        "a:has-text('登录')",
                        "button:has-text('登录')",
                        "a:has-text('Login')"
                    ]
                    for selector in login_selectors:
                        try:
                            if await page.is_visible(selector, timeout=2000):
                                await page.click(selector, timeout=5000)
                                logger.info(f"Clicked login element: {selector}")
                                await asyncio.sleep(2)
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Click login link failed: {e}")

            await take_screenshot(page, "02_login_popup")

            # Step 3: Wait for popup input fields
            logger.info("Waiting for login form inputs...")
            await page.wait_for_selector("input[type='text'], input[type='email']", timeout=10000)

            # Step 4: Locate username and password inputs
            inputs = await page.query_selector_all("input")
            username_input = None
            password_input = None

            for inp in inputs:
                input_type = await inp.get_attribute("type")
                if input_type in ("text", "email"):
                    username_input = inp
                elif input_type == "password":
                    password_input = inp

            if not username_input or not password_input:
                logger.error("Failed to locate username or password input field")
                await take_screenshot(page, "03_error_inputs")
                return 1

            # Step 5: Fill in credentials
            logger.info("Filling username...")
            await username_input.fill(username)
            logger.info("Filling password...")
            await password_input.fill(password)
            await take_screenshot(page, "03_filled_form")

            # Step 6: Submit login form
            logger.info("Submitting login form (pressing Enter)...")
            await password_input.press("Enter")
            await asyncio.sleep(5)
            await take_screenshot(page, "04_after_login")

            # Step 6.5: Close welcome modal if present
            logger.info("Checking for welcome modal popup...")
            modal_exists = await page.evaluate("""
                () => {
                    return document.querySelector('.modal.show') !== null ||
                           document.querySelector('.modal[style*="display: block"]') !== null;
                }
            """)

            if modal_exists:
                logger.info("Welcome modal detected, closing it via JavaScript...")
                await page.evaluate("""
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
                """)
                await asyncio.sleep(1)
                await take_screenshot(page, "04b_modal_closed")
            else:
                logger.info("No welcome modal found.")

            # Step 7: Check and perform sign-in
            logger.info("Checking sign-in status...")

            # 等待页面完全加载，包括 AJAX 内容
            await asyncio.sleep(3)

            # 使用精确的选择器定位签到按钮
            # 真正的可点击元素是 .tt_signpanel .btn.signBtn 这个 div
            signin_button_selector = ".tt_signpanel .btn.signBtn"
            signin_button_alt = ".tt_signpanel .btn-primary"
            signin_text_selector = "#sign_title"

            sign_button = None

            # 先尝试精确选择器
            try:
                sign_button = await page.wait_for_selector(signin_button_selector, timeout=5000)
                logger.info(f"Found sign-in button with selector: {signin_button_selector}")
            except:
                try:
                    sign_button = await page.wait_for_selector(signin_button_alt, timeout=5000)
                    logger.info(f"Found sign-in button with alt selector: {signin_button_alt}")
                except:
                    logger.warning("Sign-in button not found with primary selectors")

            # 获取签到文本状态
            sign_text = ""
            try:
                sign_text_el = await page.wait_for_selector(signin_text_selector, timeout=5000)
                if sign_text_el:
                    sign_text = await sign_text_el.inner_text()
                    logger.info(f"Current sign-in text: '{sign_text}'")
            except:
                logger.warning("Could not find #sign_title element")

            # 判断是否已签到
            if "今日已签到" in sign_text or "已签到" in sign_text:
                logger.info("Already signed in today! No action needed.")
            else:
                logger.info("Not signed in yet. Attempting to click sign-in button...")

                if sign_button:
                    # 方法1: 使用 Playwright 原生点击
                    try:
                        await sign_button.click(timeout=5000)
                        logger.info("Clicked sign-in button via Playwright")
                        await asyncio.sleep(5)
                    except Exception as e:
                        logger.warning(f"Playwright click failed: {e}")

                        # 方法2: 通过 JavaScript 点击，使用精确选择器
                        clicked = await page.evaluate("""
                            () => {
                                // 精确选择器定位签到按钮
                                var btn = document.querySelector('.tt_signpanel .btn.signBtn') || 
                                          document.querySelector('.tt_signpanel .btn-primary');
                                if (!btn) return 'button-not-found';

                                // 触发完整点击事件链
                                btn.focus();
                                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                                btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                                btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));

                                // 如果按钮有 onclick 属性，也直接调用
                                if (btn.onclick) btn.onclick();

                                return 'clicked: ' + btn.tagName + (btn.id ? '#' + btn.id : '') + 
                                       (btn.className ? '.' + btn.className.split(' ').slice(0,3).join('.') : '');
                            }
                        """)
                        logger.info(f"JavaScript click result: {clicked}")
                        await asyncio.sleep(5)
                else:
                    # 如果连按钮都没找到，尝试通过 #sign_title 向上查找
                    logger.warning("Sign button not found, trying to locate via #sign_title...")
                    clicked = await page.evaluate("""
                        () => {
                            var signTitle = document.querySelector('#sign_title');
                            if (!signTitle) return 'sign-title-not-found';

                            // 向上查找 .btn.signBtn 或 .btn-primary
                            var btn = signTitle.closest('.btn.signBtn, .btn-primary, .btn');
                            if (btn) {
                                btn.click();
                                btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                                return 'clicked-parent-btn';
                            }

                            // 再向上查找 .tt_signpanel
                            var panel = signTitle.closest('.tt_signpanel');
                            if (panel) {
                                var panelBtn = panel.querySelector('.btn');
                                if (panelBtn) {
                                    panelBtn.click();
                                    return 'clicked-panel-btn';
                                }
                            }

                            return 'no-clickable-parent-found';
                        }
                    """)
                    logger.info(f"Fallback click result: {clicked}")
                    await asyncio.sleep(5)

                await take_screenshot(page, "05_after_sign_click")

                # 再次检查签到状态
                await asyncio.sleep(3)

                try:
                    sign_text_el_after = await page.wait_for_selector(signin_text_selector, timeout=5000)
                    if sign_text_el_after:
                        sign_text_after = await sign_text_el_after.inner_text()
                        logger.info(f"Sign-in text after click: '{sign_text_after}'")
                        if "今日已签到" in sign_text_after or "已签到" in sign_text_after:
                            logger.info("Sign-in completed successfully!")
                        else:
                            logger.warning("Sign-in text does not indicate success. Checking API response...")
                            if signin_api_response.get('last'):
                                logger.info(f"API Response: {signin_api_response['last']}")
                    else:
                        logger.warning("Sign-in element disappeared after click.")
                        if signin_api_response.get('last'):
                            logger.info(f"API Response captured: {signin_api_response['last']}")
                except Exception as e:
                    logger.warning(f"Could not verify sign-in status after click: {e}")

            logger.info("Check-in workflow completed.")
            return 0

        except Exception as e:
            logger.exception(f"Unexpected error during check-in: {e}")
            if "page" in locals():
                await take_screenshot(page, "error")
            return 1

        finally:
            if browser:
                logger.info("Closing browser...")
                await browser.close()

if __name__ == "__main__":
    exit_code = asyncio.run(run_checkin())
    sys.exit(exit_code)
