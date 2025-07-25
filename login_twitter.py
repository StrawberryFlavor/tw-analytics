#!/usr/bin/env python3
"""
Twitter登录脚本 - 一次性运行保存cookies
运行后生成的cookies可供后续服务使用

支持从环境变量读取配置：
- TWITTER_USERNAME: Twitter用户名或邮箱
- TWITTER_PASSWORD: Twitter密码
- TWITTER_EMAIL: 备用邮箱（用于验证）
- PLAYWRIGHT_PROXY: 代理地址
"""

import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

# 添加src路径以便导入工具函数
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.app.core.path_manager import load_env_file, get_cookie_file_path

# 加载环境变量
load_env_file()

async def login_twitter():
    """登录Twitter并保存cookies"""
    
    # 从环境变量获取配置，如果没有则提示输入
    username = os.getenv('TWITTER_USERNAME')
    if not username:
        username = input("请输入Twitter用户名/邮箱: ").strip()
    else:
        print(f"👤 使用环境变量中的用户名: {username}")
    
    password = os.getenv('TWITTER_PASSWORD')
    if not password:
        password = input("请输入密码: ").strip()
    else:
        print("🔐 使用环境变量中的密码")
    
    email = os.getenv('TWITTER_EMAIL')
    if not email:
        email = input("请输入备用邮箱(可选，回车跳过): ").strip() or None
    else:
        print(f"📧 使用环境变量中的备用邮箱: {email}")
    
    # Only use proxy if explicitly set via PLAYWRIGHT_PROXY
    proxy = os.getenv('PLAYWRIGHT_PROXY')
    if not proxy:
        proxy = input("请输入代理地址(可选，回车跳过): ").strip() or None
    else:
        print(f"🌐 使用环境变量代理: {proxy}")
    cookies_file = get_cookie_file_path()
    
    print(f"\n🚀 开始登录Twitter...")
    
    # 启动playwright
    playwright = await async_playwright().start()
    
    # 配置浏览器 - 使用更现代的User-Agent和参数
    headless = os.getenv('PLAYWRIGHT_HEADLESS', 'false').lower() == 'true'  # 登录默认显示窗口
    browser_args = {
        "headless": headless,
        "args": [
            "--no-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor"
        ]
    }
    
    if proxy:
        # Ensure proxy URL is properly formatted
        if not proxy.startswith(('http://', 'https://', 'socks5://')):
            proxy = f"http://{proxy}"
        browser_args["proxy"] = {"server": proxy}
        print(f"🌐 配置代理为: {proxy}")
    
    browser = await playwright.chromium.launch(**browser_args)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        }
    )
    
    page = await context.new_page()
    
    try:
        # 访问登录页面
        print("📱 访问登录页面...")
        await page.goto("https://x.com/i/flow/login", timeout=30000)
        
        # 输入用户名
        print("👤 输入用户名...")
        await page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
        await page.fill('input[autocomplete="username"]', username)
        await page.click('button:has-text("下一步"), button:has-text("Next")')
        
        await asyncio.sleep(2)
        
        # 检查是否需要邮箱验证
        email_input = await page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
        if email_input and email:
            print("📧 需要邮箱验证...")
            await page.fill('input[data-testid="ocfEnterTextTextInput"]', email)
            await page.click('[data-testid="ocfEnterTextNextButton"]')
            await asyncio.sleep(2)
        
        # 输入密码
        print("🔐 输入密码...")
        await page.wait_for_selector('input[name="password"]', timeout=10000)
        await page.fill('input[name="password"]', password)
        await page.click('[data-testid="LoginForm_Login_Button"]')
        
        # 等待登录完成
        print("⏳ 等待登录完成...")
        await asyncio.sleep(5)
        
        # 检查是否成功
        current_url = page.url
        if "home" in current_url or "x.com" in current_url:
            print("✅ 登录成功!")
            
            # 保存cookies
            cookies = await context.cookies()
            os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
            
            with open(cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            
            print(f"🍪 Cookies已保存到: {cookies_file}")
            print("📝 现在可以使用这些cookies启动服务了")
            
            return True
        else:
            print("❌ 登录失败，请检查凭据或处理验证码")
            return False
            
    except Exception as e:
        print(f"❌ 登录过程出错: {e}")
        return False
        
    finally:
        input("\n按回车键关闭浏览器...")
        await browser.close()
        await playwright.stop()

if __name__ == "__main__":
    print("=" * 50)
    print("Twitter登录工具")
    print("用于一次性登录并保存cookies供服务使用")
    print("=" * 50)
    
    success = asyncio.run(login_twitter())
    
    if success:
        print("\n🎉 设置完成! 现在可以启动服务:")
        print("  本地: python run.py")
        print("  Docker: docker run -v $(pwd)/instance:/app/instance tw-analytics-app")
    else:
        print("\n❌ 登录失败，请重试")