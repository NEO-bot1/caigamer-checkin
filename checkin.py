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
                    await page.click("a[href*='login']", timeout=10000)
                    await asyncio.sleep(2)
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
                        // Method 1: Bootstrap 5 API
                        var modalEl = document.querySelector('.modal.show');
                        if (modalEl && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                            var modal = bootstrap.Modal.getInstance(modalEl);
                            if (modal) modal.hide();
                        }
                        // Method 2: Force hide all modals and remove backdrop
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
            logger.info("Checking sign-in status (#sign_title)...")
            sign_element = await page.query_selector("#sign_title")

            if not sign_element:
                logger.warning("Sign-in element #sign_title not found on page")
                await take_screenshot(page, "05_no_sign_element")
                return 0

            sign_text = await sign_element.inner_text()
            logger.info(f"Current sign-in text: '{sign_text}'")

            if "今日已签到" in sign_text:
                logger.info("Already signed in today! No action needed.")
            else:
                logger.info("Not signed in yet. Attempting to click sign-in element...")
                try:
                    await sign_element.click()
                    await asyncio.sleep(3)
                    await take_screenshot(page, "05_after_sign_click")

                    # Verify sign-in success
                    sign_element = await page.query_selector("#sign_title")
                    if sign_element:
                        sign_text = await sign_element.inner_text()
                        logger.info(f"Sign-in text after click: '{sign_text}'")
                        if "今日已签到" in sign_text:
                            logger.info("Sign-in completed successfully!")
                        else:
                            logger.warning("Sign-in text does not indicate success. Please verify manually.")
                    else:
                        logger.warning("Sign-in element disappeared after click.")
                except Exception as e:
                    logger.error(f"Failed to click sign-in element: {e}")
                    await take_screenshot(page, "05_sign_error")

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
