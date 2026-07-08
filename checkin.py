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
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            print(f"[{datetime.now()}] 访问网站...")
            await page.goto("https://caigamer.cn/", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # 截图查看当前页面状态
            await page.screenshot(path="page_start.png")
            print("已截图: page_start.png")
            
            # 查找登录入口
            print("查找登录按钮...")
            # 常见登录按钮文本
            login_selectors = [
                "a[href*='login']",
                "text=登录",
                "text=登入",
                "text=Sign in",
                ".login",
                "#login",
                "[class*='login']"
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
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await page.screenshot(path="page_login.png")
                print("已截图: page_login.png")
            else:
                print("未找到登录按钮，可能已登录或页面结构不同")
            
            # 检查当前页面
            print(f"当前URL: {page.url}")
            print(f"页面标题: {await page.title()}")
            
            # 查找签到元素
            print("查找签到元素...")
            sign_selectors = [
                "#sign_title",
                ".sign-btn",
                "#sign-btn",
                "[class*='sign']",
                "text=签到",
                "text=每日签到"
            ]
            
            sign_el = None
            for sel in sign_selectors:
                try:
                    sign_el = await page.query_selector(sel)
                    if sign_el:
                        text = await sign_el.inner_text()
                        print(f"找到元素: {sel}, 文本: {text}")
                        break
                except:
                    continue
            
            if sign_el:
                text = await sign_el.inner_text()
                if "已签到" in text:
                    print("今日已签到")
                else:
                    print("点击签到...")
                    await sign_el.click()
                    await asyncio.sleep(2)
                    print("签到完成")
            else:
                print("未找到签到元素")
            
            await page.screenshot(path="page_final.png")
            print("已截图: page_final.png")
            
        except Exception as e:
            print(f"错误: {e}")
            await page.screenshot(path="error.png")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(checkin())
