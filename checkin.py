import asyncio
import os
import sys
import logging
import json
import re
import glob
import smtplib
import ssl
import traceback
from datetime import datetime
from email.message import EmailMessage
from playwright.async_api import async_playwright

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("caigamer_checkin")

async def take_screenshot(page, step_name, account_name=None):
    """Take a screenshot and save with timestamp. Optionally include account name."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = None
    if account_name:
        safe_name = re.sub(r"[^0-9A-Za-z_-]", "", account_name)
        filename = f"page_{safe_name}_{step_name}_{timestamp}.png"
    else:
        filename = f"page_{step_name}_{timestamp}.png"
    await page.screenshot(path=filename, full_page=True)
    logger.info(f"Screenshot saved: {filename}")
    return filename


def get_accounts_from_env():
    """Collect accounts from environment.

    Support two modes:
    - `CAIGAMER_ACCOUNTS` JSON: [{"username":"u","password":"p"}, ...]
    - Numbered env vars: CAIGAMER_USERNAME, CAIGAMER_PASSWORD, CAIGAMER_USERNAME_2, ...
    """
    accounts = []
    raw = os.environ.get("CAIGAMER_ACCOUNTS")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    u = item.get("username")
                    p = item.get("password")
                    if u and p:
                        accounts.append({"username": u, "password": p})
        except Exception:
            logger.warning("Failed to parse CAIGAMER_ACCOUNTS JSON; falling back to individual vars")

    if not accounts:
        # Try numbered variables
        for i in range(1, 11):
            suffix = "" if i == 1 else f"_{i}"
            u = os.environ.get(f"CAIGAMER_USERNAME{suffix}")
            p = os.environ.get(f"CAIGAMER_PASSWORD{suffix}")
            if u and p:
                accounts.append({"username": u, "password": p})

    return accounts


def send_error_email(subject, body, attachments=None):
    """Send an email using SMTP settings from environment. Attach files if provided."""
    smtp_server = os.environ.get("EMAIL_SMTP_SERVER")
    smtp_port = os.environ.get("EMAIL_SMTP_PORT")
    smtp_user = os.environ.get("EMAIL_USERNAME")
    smtp_pass = os.environ.get("EMAIL_PASSWORD")
    email_to = os.environ.get("EMAIL_TO")
    email_from = os.environ.get("EMAIL_FROM") or smtp_user

    if not (smtp_server and smtp_port and smtp_user and smtp_pass and email_to):
        logger.warning("Email not sent: SMTP configuration or recipient missing in environment")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_from
        msg["To"] = email_to
        msg.set_content(body)

        # Attach files
        if attachments:
            for path in attachments:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    maintype = "application"
                    subtype = "octet-stream"
                    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(path))
                except Exception as e:
                    logger.warning(f"Failed to attach {path}: {e}")

        port = int(smtp_port)
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, port, timeout=60) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        logger.info("Error email sent successfully")
        return True
    except Exception as e:
        logger.exception(f"Failed to send error email: {e}")
        return False

async def run_checkin():
    """Main check-in workflow supporting multiple accounts and email notifications on failure."""
    accounts = get_accounts_from_env()
    # Limit to at most 3 accounts
    if len(accounts) > 3:
        logger.info(f"Limiting accounts to first 3 (found {len(accounts)})")
        accounts = accounts[:3]
    if not accounts:
        logger.error("No accounts found in environment. Set CAIGAMER_ACCOUNTS or CAIGAMER_USERNAME/CAIGAMER_PASSWORD variables.")
        return 1

    results = []
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

            for acct in accounts:
                username = acct.get("username")
                password = acct.get("password")
                acct_result = {"username": username, "success": False, "error": None}
                try:
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN",
                        timezone_id="Asia/Shanghai"
                    )
                    page = await context.new_page()

                    logger.info(f"[{username}] Navigating to https://caigamer.cn/ ...")
                    await page.goto("https://caigamer.cn/", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(2)
                    await take_screenshot(page, "01_homepage", account_name=username)

                    # Handle login popup
                    logger.info(f"[{username}] Checking if login popup is already visible...")
                    all_inputs = await page.query_selector_all("input")
                    has_text_input = False
                    has_password_input = False
                    for inp in all_inputs:
                        input_type = await inp.get_attribute("type")
                        if input_type in ("text", "email"):
                            has_text_input = True
                        elif input_type == "password":
                            has_password_input = True

                    if not (has_text_input and has_password_input):
                        logger.info(f"[{username}] Login popup not auto-shown, trying login link...")
                        try:
                            await page.click("a[href*='login']", timeout=8000)
                            await asyncio.sleep(1)
                        except Exception as e:
                            logger.warning(f"[{username}] Click login link failed: {e}")

                    await take_screenshot(page, "02_login_popup", account_name=username)

                    # Wait for inputs
                    await page.wait_for_selector("input[type='text'], input[type='email']", timeout=10000)
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
                        msg = "Failed to locate username or password input field"
                        logger.error(f"[{username}] {msg}")
                        await take_screenshot(page, "03_error_inputs", account_name=username)
                        acct_result.update({"error": msg})
                        results.append(acct_result)
                        await context.close()
                        continue

                    await username_input.fill(username)
                    await password_input.fill(password)
                    await take_screenshot(page, "03_filled_form", account_name=username)

                    await password_input.press("Enter")
                    await asyncio.sleep(4)
                    await take_screenshot(page, "04_after_login", account_name=username)

                    # Close welcome modal if present
                    modal_exists = await page.evaluate("""
                        () => {
                            return document.querySelector('.modal.show') !== null ||
                                   document.querySelector('.modal[style*="display: block"]') !== null;
                        }
                    """)
                    if modal_exists:
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
                        await take_screenshot(page, "04b_modal_closed", account_name=username)

                    # Sign-in
                    logger.info(f"[{username}] Checking sign-in status (#sign_title)...")
                    sign_element = await page.query_selector("#sign_title")
                    if not sign_element:
                        msg = "Sign-in element #sign_title not found"
                        logger.warning(f"[{username}] {msg}")
                        await take_screenshot(page, "05_no_sign_element", account_name=username)
                        acct_result.update({"error": msg})
                        results.append(acct_result)
                        await context.close()
                        continue

                    sign_text = await sign_element.inner_text()
                    logger.info(f"[{username}] Current sign-in text: '{sign_text}'")

                    if "今日已签到" in sign_text:
                        logger.info(f"[{username}] Already signed in today.")
                        acct_result.update({"success": True})
                    else:
                        clicked = await page.evaluate("""
                            () => {
                                var el = document.querySelector('#sign_title');
                                if (!el) return 'not-found';
                                var parent = el.closest('a, button, [onclick], .btn, [data-toggle]');
                                if (parent) { parent.click(); return 'clicked-parent'; }
                                el.click();
                                var evt = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
                                el.dispatchEvent(evt);
                                return 'clicked-self';
                            }
                        """)
                        logger.info(f"[{username}] Click result: {clicked}")
                        await asyncio.sleep(4)
                        await take_screenshot(page, "05_after_sign_click", account_name=username)
                        sign_element = await page.query_selector("#sign_title")
                        if sign_element:
                            sign_text = await sign_element.inner_text()
                            if "今日已签到" in sign_text:
                                logger.info(f"[{username}] Sign-in completed successfully")
                                acct_result.update({"success": True})
                            else:
                                msg = "Sign-in did not indicate success after click"
                                logger.warning(f"[{username}] {msg}")
                                acct_result.update({"error": msg})
                        else:
                            msg = "Sign-in element disappeared after click"
                            logger.warning(f"[{username}] {msg}")
                            acct_result.update({"error": msg})

                    results.append(acct_result)
                    await context.close()

                except Exception as e:
                    err = traceback.format_exc()
                    logger.exception(f"Unexpected error for account {username}: {e}")
                    try:
                        if 'page' in locals():
                            await take_screenshot(page, "error", account_name=username)
                    except Exception:
                        logger.exception("Failed to capture error screenshot")
                    acct_result.update({"error": str(e)})
                    results.append(acct_result)

            return_code = 0
            # If there are errors, attempt to send summary email
            failed = [r for r in results if not r.get('success')]
            if failed:
                body_lines = ["Check-in run completed with failures:\n"]
                for r in results:
                    status = "OK" if r.get('success') else f"ERROR: {r.get('error') }"
                    body_lines.append(f"- {r.get('username')}: {status}")
                body = "\n".join(body_lines)
                # Attach recent screenshots
                attachments = sorted(glob.glob('page_*.png'), reverse=True)[:10]
                send_error_email("Caigamer check-in: failures detected", body, attachments=attachments)
                return_code = 1

            logger.info("All accounts processed.")
            return return_code

        except Exception as e:
            logger.exception(f"Unexpected error during check-in run: {e}")
            # send email with traceback
            tb = traceback.format_exc()
            attachments = sorted(glob.glob('page_*.png'), reverse=True)[:10]
            send_error_email("Caigamer check-in: unexpected failure", tb, attachments=attachments)
            return 1

        finally:
            if browser:
                logger.info("Closing browser...")
                await browser.close()

if __name__ == "__main__":
    exit_code = asyncio.run(run_checkin())
    sys.exit(exit_code)
