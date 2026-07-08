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
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        try:
            print(f"[{datetime.now()}] 访问网站...")
            
            # 只等待 DOM 加载，不等待所有资源
            await page.goto("https://caigamer.cn/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            await page.screenshot(path="page_start.png")
            print("已截图: page_start.png")
            
            # 查找并点击登录按钮
            print("查找登录按钮...")
            login_btn = await page.query_selector("a[href*='login']")
            
            if login_btn:
                print("找到登录按钮，点击...")
                await login_btn.click()
                await asyncio.sleep(2)  # 等待弹窗动画
                
                # 不等待页面加载，直接截图看弹窗
                await page.screenshot(path="page_login_popup.png")
                print("已截图: page_login_popup.png")
                
                # 等待弹窗中的输入框出现
                print("等待登录表单...")
                await page.wait_for_selector("input[type='text'], input[type='email'], input[name='username'], input[name='email'], input[placeholder*='邮箱'], input[placeholder*='用户名'], input[placeholder*='email']", timeout=10000)
                await asyncio.sleep(1)
                
                # 查找输入框
                print("查找输入框...")
                all_inputs = await page.query_selector_all("input")
                print(f"找到 {len(all_inputs)} 个 input 元素")
                
                username_input = None
                password_input = None
                
                for inp in all_inputs:
                    input_type = await inp.get_attribute("type") or ""
                    input_name = await inp.get_attribute("name") or ""
                    placeholder = await inp.get_attribute("placeholder") or ""
                    
                    print(f"input: type={input_type}, name={input_name}, placeholder={placeholder}")
                    
                    if not username_input and input_type in ["text", "email"]:
                        username_input = inp
                    elif not password_input and input_type == "password":
                        password_input = inp
                
                if username_input and password_input:
                    print("填写登录信息...")
                    await username_input.fill(USERNAME)
                    await password_input.fill(PASSWORD)
                    await asyncio.sleep(1)
                    
                    # 查找提交按钮
                    submit_btn = await page.query_selector("button[type='submit'], button:has-text('登录'), button:has-text('登入'), button:has-text('Submit'), .submit, #submit, button[class*='submit']")
                    
                    if submit_btn:
                        print("点击提交按钮...")
                        await submit_btn.click()
                    else:
                        print("未找到提交按钮，按回车...")
                        await password_input.press("Enter")
                    
                    await asyncio.sleep(3)
                    await page.screenshot(path="page_after_login.png")
                    print("登录后截图保存")
                else:
                    print(f"未找到输入框: username={username_input is not None}, password={password_input is not None}")
                    await page.screenshot(path="page_no_inputs.png")
            else:
                print("未找到登录按钮，检查是否已登录")
            
            # 检查当前状态
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
                    
                    await page.reload()
                    await asyncio.sleep(2)
                    await page.screenshot(path="page_after_sign.png")
            else:
                print("未找到签到元素")
            
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
