#!/usr/bin/env python3
"""
Cookie管理功能示例
展示如何使用新的Cookie持久化策略
"""

import asyncio
import os
import sys
import requests
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.app.services.cookie_manager import get_cookie_manager


async def demo_cookie_manager():
    """演示Cookie管理器功能"""
    print("🍪 Cookie管理器功能演示")
    print("=" * 50)
    
    # 获取Cookie管理器实例
    cookie_manager = get_cookie_manager()
    
    # 1. 检查Cookie状态
    print("1. 检查当前Cookie状态:")
    status = cookie_manager.get_cookie_status()
    print(f"   - 文件存在: {status['file_exists']}")
    print(f"   - 上次验证: {status['last_validation'] or '从未验证'}")
    print(f"   - 文件年龄: {status['file_age_hours']}小时" if status['file_age_hours'] else "   - 文件年龄: N/A")
    print(f"   - 需要验证: {status['needs_validation']}")
    
    print("\n2. 获取有效Cookie:")
    try:
        cookies = await cookie_manager.get_valid_cookies()
        if cookies:
            print(f"   ✅ 成功获取 {len(cookies)} 个有效Cookie")
        else:
            print("   ❌ 未能获取有效Cookie")
    except Exception as e:
        print(f"   ❌ 获取Cookie时出错: {e}")
    
    print("\n演示完成!")


def demo_api_endpoints():
    """演示API端点"""
    print("\n🔌 API端点演示")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:5100"
    
    # 1. 检查认证状态
    print("1. 检查认证状态:")
    try:
        response = requests.get(f"{base_url}/api/v1/auth/status")
        if response.status_code == 200:
            data = response.json()
            auth_data = data['data']['authentication']
            print(f"   - 状态: {data['data']['status']}")
            print(f"   - Cookie文件存在: {auth_data['cookie_file_exists']}")
            print(f"   - 自动刷新启用: {auth_data['auto_refresh_enabled']}")
            print(f"   - 文件年龄: {auth_data['file_age_hours']}小时" if auth_data['file_age_hours'] else "   - 文件年龄: N/A")
        else:
            print(f"   ❌ API请求失败: {response.status_code}")
    except requests.RequestException as e:
        print(f"   ❌ 无法连接到API: {e}")
        print("   请确保服务已启动: python run.py")
        return
    
    # 2. 强制刷新Cookie (仅在有凭据时)
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    
    if username and password:
        print("\n2. 测试强制刷新Cookie:")
        choice = input("   是否要测试强制刷新Cookie? (y/N): ").lower()
        if choice == 'y':
            try:
                response = requests.post(f"{base_url}/api/v1/auth/refresh")
                if response.status_code == 200:
                    print("   ✅ Cookie刷新成功")
                else:
                    data = response.json()
                    print(f"   ❌ Cookie刷新失败: {data.get('message', '未知错误')}")
            except requests.RequestException as e:
                print(f"   ❌ 刷新请求失败: {e}")
    else:
        print("\n2. 跳过Cookie刷新测试 (需要TWITTER_USERNAME和TWITTER_PASSWORD环境变量)")


def main():
    """主函数"""
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Twitter Cookie管理功能演示\n")
    
    # 检查环境变量
    username = os.getenv('TWITTER_USERNAME')
    if username:
        print(f"✅ 检测到登录凭据: {username}")
    else:
        print("⚠️  未检测到TWITTER_USERNAME环境变量")
        print("   Cookie自动刷新功能将不可用")
    
    # 演示Cookie管理器
    print("\n" + "="*60)
    asyncio.run(demo_cookie_manager())
    
    # 演示API端点
    print("\n" + "="*60)
    demo_api_endpoints()
    
    print("\n" + "="*60)
    print("演示结束!")
    print("\n💡 使用提示:")
    print("1. 配置TWITTER_USERNAME和TWITTER_PASSWORD环境变量启用自动刷新")
    print("2. 使用 /api/v1/auth/status 监控Cookie状态")
    print("3. 使用 /api/v1/auth/refresh 手动刷新Cookie")
    print("4. 系统会每小时自动检查Cookie有效性")


if __name__ == "__main__":
    main()