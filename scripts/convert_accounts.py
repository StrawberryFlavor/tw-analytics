#!/usr/bin/env python3
"""
账户格式转换脚本
将 scripts/accounts.json 的账户转换为系统标准格式并合并到 src/config/accounts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

def load_source_accounts(source_path):
    """加载源账户文件"""
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('accounts', [])
    except Exception as e:
        print(f"❌ 加载源文件失败: {e}")
        return []

def load_target_accounts(target_path):
    """加载目标账户文件"""
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('accounts', []), data.get('metadata', {})
    except FileNotFoundError:
        # 文件不存在，返回空列表和默认元数据
        return [], {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "total_accounts": 0
        }
    except Exception as e:
        print(f"❌ 加载目标文件失败: {e}")
        return [], {}

def convert_account(source_account):
    """转换单个账户格式"""
    now = datetime.now().isoformat()
    
    # 基础字段映射
    converted = {
        "username": source_account.get("username", ""),
        "password": source_account.get("password", ""),
        "email": source_account.get("email", ""),
        "email_password": source_account.get("email_password", ""),
        "phone_suffix": source_account.get("phone_suffix", ""),
        "tfa_secret": source_account.get("tfa_secret", ""),
        "auth_token": source_account.get("auth_token", ""),
        "status": source_account.get("status", "active"),
        "last_used": None,  # 新账户未使用过
        "created_at": now,
        "updated_at": now,
        "metadata": {
            "source": "scripts_import",
            "import_time": now
        }
    }
    
    # 如果有backup_code，保存到metadata中
    if source_account.get("backup_code"):
        converted["metadata"]["backup_code"] = source_account["backup_code"]
    
    return converted

def main():
    """主函数"""
    print("🔄 账户格式转换脚本")
    print("=" * 50)
    
    # 文件路径
    script_dir = Path(__file__).parent
    source_path = script_dir / "accounts.json"
    target_path = script_dir.parent / "src" / "config" / "accounts.json"
    
    print(f"📂 源文件: {source_path}")
    print(f"📂 目标文件: {target_path}")
    
    # 自动执行模式
    print("\n🚀 自动执行账户转换...")
    
    # 加载源账户
    print("\n📖 加载源账户...")
    source_accounts = load_source_accounts(source_path)
    if not source_accounts:
        print("❌ 没有找到源账户")
        return
    
    print(f"✅ 找到 {len(source_accounts)} 个源账户")
    
    # 加载目标账户
    print("📖 加载目标账户...")
    target_accounts, metadata = load_target_accounts(target_path)
    print(f"✅ 找到 {len(target_accounts)} 个现有账户")
    
    # 获取现有用户名集合
    existing_usernames = {acc.get("username") for acc in target_accounts}
    
    # 转换并合并账户
    print("\n🔄 转换账户格式...")
    converted_accounts = []
    skipped_count = 0
    
    for source_account in source_accounts:
        username = source_account.get("username")
        
        if username in existing_usernames:
            print(f"⏭️  跳过重复账户: {username}")
            skipped_count += 1
            continue
        
        converted = convert_account(source_account)
        converted_accounts.append(converted)
        existing_usernames.add(username)  # 防止源文件内部重复
    
    print(f"✅ 转换完成: {len(converted_accounts)} 个新账户")
    print(f"⏭️  跳过重复: {skipped_count} 个账户")
    
    if not converted_accounts:
        print("❌ 没有新账户需要添加")
        return
    
    # 合并账户列表
    all_accounts = target_accounts + converted_accounts
    
    # 更新元数据
    metadata.update({
        "version": "1.0",
        "last_updated": datetime.now().isoformat(),
        "total_accounts": len(all_accounts)
    })
    
    # 构建最终数据
    final_data = {
        "accounts": all_accounts,
        "metadata": metadata
    }
    
    # 备份原文件
    if target_path.exists():
        backup_path = target_path.with_suffix(f'.bak.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        target_path.rename(backup_path)
        print(f"💾 原文件已备份: {backup_path}")
    
    # 保存新文件
    print(f"\n💾 保存到: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)
    
    print("✅ 转换完成！")
    print("\n📊 最终统计:")
    print(f"   总账户数: {len(all_accounts)}")
    print(f"   新增账户: {len(converted_accounts)}")
    print(f"   现有账户: {len(target_accounts)}")
    print(f"   跳过重复: {skipped_count}")
    
    # 验证结果
    print("\n🔍 验证转换结果...")
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            verification_data = json.load(f)
        
        accounts_count = len(verification_data.get('accounts', []))
        metadata_count = verification_data.get('metadata', {}).get('total_accounts', 0)
        
        if accounts_count == metadata_count == len(all_accounts):
            print("✅ 验证通过，文件格式正确")
        else:
            print(f"⚠️  验证警告: 数量不匹配 (accounts: {accounts_count}, metadata: {metadata_count}, expected: {len(all_accounts)})")
            
    except Exception as e:
        print(f"❌ 验证失败: {e}")

if __name__ == "__main__":
    main()