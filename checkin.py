#!/usr/bin/env python3
import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

USERNAME = os.environ.get("CAIGAMER_USERNAME")
PASSWORD = os.environ.get("CAIGAMER_PASSWORD")

async def checkin():
    if not USERNAME or not PASSWORD:
        print("错误：请设置环境变量")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
        )
        
        page = await context.new_page()
        
        try:
            print(f"[{datetime.now()}] 访问网站...")
            
            # 增加超时到 60 秒
            await page.goto("https://caigamer.cn/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            await page.screenshot(path="page_start.png")
            print("已截图: page_start.png")
            
            # 检查是否已经登录（看右上角是否有用户头像/用户名）
            print("检查登录状态...")
            user_element = await page.query_selector(".user-name, .avatar, [class*='user']")
            
            if user_element:
                print("可能已经登录")
            else:
                print("未登录，尝试点击登录按钮...")
                
                # 查找登录按钮（多种可能）
                login_selectors = [
                    "text=登录",
                    "text=登入",
                    "text=Sign in",
                    ".login",
                    "#login",
                    "a[href*='login']",
                    "[class*='login']",
                    "button:has-text('登录')",
                    "button:has-text('登入')"
                ]
                
                login_btn = None
                for sel in login_selectors:
                    try:
                        login_btn = await page.query_selector(sel)
                        if login_btn:
                            print(f"找到登录按钮: {sel}")
                            break
                    except:
                        continue
                
                if login_btn:
                    await login_btn.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path="page_login_clicked.png")
                    print("已点击登录，截图保存")
                    
                    # 等待弹窗出现
                    print("等待登录弹窗...")
                    await page.wait_for_selector("input[type='text'], input[type='email'], input[name='username'], input[name='email'], input[placeholder*='邮箱'], input[placeholder*='用户名']", timeout=10000)
                    await asyncio.sleep(1)
                    
                    # 填写登录表单
                    print("填写登录信息...")
                    
                    # 查找用户名输入框
                    username_input = await page.query_selector("input[type='text'], input[type='email'], input[name='username'], input[name='email'], input[placeholder*='邮箱'], input[placeholder*='用户名']")
                    password_input = await page.query_selector("input[type='password'], input[name='password']")
                    
                    if username_input and password_input:
                        await username_input.fill(USERNAME)
                        await password_input.fill(PASSWORD)
                        await asyncio.sleep(1)
                        
                        # 点击登录提交
                        submit_btn = await page.query_selector("button[type='submit'], button:has-text('登录'), button:has-text('登入'), button:has-text('Submit'), .submit, #submit")
                        if submit_btn:
                            await submit_btn.click()
                            print("已提交登录")
                        else:
                            # 尝试按回车
                            await password_input.press("Enter")
                            print("按回车提交")
                        
                        await asyncio.sleep(3)
                        await page.screenshot(path="page_after_login.png")
                        print("登录后截图保存")
                    else:
                        print("未找到登录表单输入框")
                        await page.screenshot(path="page_no_form.png")
                else:
                    print("未找到登录按钮")
            
            # 再次检查登录状态
            print(f"当前URL: {page.url}")
            await page.screenshot(path="page_before_sign.png")
            
            # 查找签到元素
            print("查找签到元素...")
            sign_selectors = [
                "#sign_title",
                ".sign-btn",
                "#sign-btn",
                "[class*='sign']",
                "text=签到",
                "text=每日签到",
                "text=今日已签到",
                "text=已签到"
            ]
            
            sign_el = None
            sign_text = ""
            for sel in sign_selectors:
                try:
                    sign_el = await page.query_selector(sel)
                    if sign_el:
                        sign_text = await sign_el.inner_text()
                        print(f"找到元素: {sel}, 文本: {sign_text}")
                        break
                except Exception as e:
                    print(f"选择器 {sel} 失败: {e}")
                    continue
            
            if sign_el:
                if "已签到" in sign_text:
                    print("今日已签到，无需操作")
                else:
                    print("点击签到...")
                    await sign_el.click()
                    await asyncio.sleep(2)
                    print("签到完成")
                    
                    # 验证
                    await page.reload()
                    await asyncio.sleep(2)
                    await page.screenshot(path="page_after_sign.png")
            else:
                print("未找到签到元素，可能页面结构不同")
                # 尝试查找包含"签到"文本的任何元素
                all_elements = await page.query_selector_all("*")
                for el in all_elements:
                    try:
                        text = await el.inner_text()
                        if "签到" in text:
                            print(f"找到包含'签到'的元素: {text}")
                            break
                    except:
                        continue
            
            await page.screenshot(path="page_final.png")
            print("最终截图保存")
            
        except Exception as e:
            print(f"错误: {str(e)}")
            try:
                await page.screenshot(path="error.png")
            except:
                pass
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(checkin())
