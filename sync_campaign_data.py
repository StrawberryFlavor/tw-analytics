#!/usr/bin/env python3
"""
数据同步脚本

从 campaign_task_submission 同步数据到 campaign_tweet_snapshot
"""

import asyncio
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def main():
    """数据同步主函数"""
    sync_service = None
    
    try:
        print("开始数据同步...")
        
        # 检查命令行参数
        dry_run = '--dry-run' in sys.argv or '--test' in sys.argv
        enable_twitter = '--no-twitter' not in sys.argv
        update_all = '--update-all' in sys.argv
        priority_new = '--priority-new' in sys.argv
        
        if dry_run:
            print("演练模式：不修改数据库")
        if not enable_twitter:
            print("禁用 Twitter API 数据获取")
        if update_all:
            print("模式：全部更新（刷新所有现有记录）")
        if priority_new:
            print("模式：优先级（处理从未同步过的数据）")
        
        print()
        
        # 1. 创建服务
        from src.app.services.database import get_database_service
        from src.app.services.data_sync import CampaignDataSyncService
        from src.app.core.config_factory import SyncConfig
        
        db_service = await get_database_service()
        
        # 创建同步配置
        if update_all:
            config = SyncConfig.create_update_all_config()
            print("使用全部更新配置")
        elif priority_new:
            config = SyncConfig.create_priority_config()
            print("使用优先级同步配置")
        else:
            config = SyncConfig.create_safe_config()
            print("使用标准同步配置")
        
        config.dry_run = dry_run
        config.enable_twitter_api = enable_twitter
        
        sync_service = CampaignDataSyncService(
            database_service=db_service,
            config=config
        )
        
        print("同步配置:")
        print(f"   批次大小: {config.sync_batch_size}")
        print(f"   最大并发: {config.max_concurrent_syncs}")
        print(f"   重试延迟: {config.sync_retry_delay}秒")
        print(f"   演练模式: {'是' if config.dry_run else '否'}")
        print(f"   Twitter API: {'启用' if config.enable_twitter_api else '禁用'}")
        print(f"   同步模式: {config.sync_mode}")
        print()
        
        # 确认执行
        if not dry_run:
            if update_all:
                print("警告：这将更新所有现有推文记录的 Twitter 数据")
                confirm = input("确认要执行全部更新吗？这可能需要较长时间 (y/N): ").strip().lower()
            elif priority_new:
                print("优先级同步：将创建所有从未同步过的推文记录")
                confirm = input("确认要执行优先级同步吗？(y/N): ").strip().lower()
            else:
                confirm = input("确认要执行数据同步吗？这将修改数据库 (y/N): ").strip().lower()
            
            if confirm != 'y':
                print("操作已取消")
                return
            print()
        
        # 2. 执行同步
        result = await sync_service.sync_all_data()
        
        # 3. 显示结果
        print("同步完成，结果：")
        print(f"   总处理记录: {result.total_processed}")
        print(f"   创建记录: {result.created_count}")
        print(f"   更新记录: {result.updated_count}")
        print(f"   跳过记录: {result.skipped_count}")
        print(f"   错误记录: {result.error_count}")
        print(f"   成功率: {result.success_rate:.1f}%")
        print(f"   处理时间: {result.processing_time:.1f}秒")
        
        if result.errors:
            print(f"\\n错误信息 ({len(result.errors)}):")
            for error in result.errors[:5]:  # 只显示前5个错误
                print(f"   - {error}")
            if len(result.errors) > 5:
                print(f"   ... 还有 {len(result.errors) - 5} 个错误")
        
        if result.error_count == 0:
            print("状态：完全成功")
        elif result.success_rate >= 80:
            print("状态：基本成功（少量错误）")
        else:
            print("状态：存在较多问题，请检查错误信息")
        
        # 4. 验证结果（非演练模式）
        if not dry_run and result.created_count > 0:
            print("\\n验证同步结果...")
            await verify_sync_results()
        
    except KeyboardInterrupt:
        print("\\n用户中断操作")
    except Exception as e:
        print(f"同步过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        if sync_service:
            try:
                print("正在清理服务资源...")
                # 清理Twitter服务资源
                await sync_service.cleanup()
                print("Twitter 服务资源清理完成")
            except Exception as e:
                print(f"Twitter 服务清理时出错: {e}")
            
            # 清理数据库连接
            if hasattr(sync_service, 'db_service'):
                try:
                    await sync_service.db_service.close()
                    print("数据库连接已关闭")
                except Exception as e:
                    print(f"数据库清理时出错: {e}")
        
        print("资源清理完成")

async def verify_sync_results():
    """验证同步结果"""
    from src.app.services.database import get_database_service
    
    db_service = await get_database_service()
    
    try:
        # 统计当前数据
        stats = await db_service.get_statistics()
        print(f"   campaign_tweet_snapshot 当前记录数: {stats['total_records']}")
        print(f"   数据完整性: {stats['success_rate']}%")
        
        # 检查最新创建的几条记录
        import aiomysql
        connection = await aiomysql.connect(
            host='nine-mysql-production.c94eqyo4iffa.ap-southeast-1.rds.amazonaws.com',
            port=3306,
            user='admin',
            password='NINE2025ai',
            db='Binineex'
        )
        
        cursor = await connection.cursor(aiomysql.DictCursor)
        await cursor.execute('''
            SELECT tweet_id, views, created_at 
            FROM campaign_tweet_snapshot 
            WHERE message LIKE '%campaign_task_submission%'
            ORDER BY created_at DESC 
            LIMIT 3
        ''')
        
        recent_records = await cursor.fetchall()
        
        if recent_records:
            print("   最新同步的记录样本:")
            for record in recent_records:
                print(f"     推文ID: {record['tweet_id']}, views: {record['views']}")
        
        await cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"   验证失败: {e}")
    finally:
        await db_service.close()

def show_help():
    """显示帮助信息"""
    print("数据同步脚本 - campaign_task_submission -> campaign_tweet_snapshot")
    print()
    print("用法:")
    print("  python sync_campaign_data.py [选项]")
    print()
    print("选项:")
    print("  --dry-run, --test      演练模式，不实际修改数据库")
    print("  --no-twitter           禁用Twitter API数据获取")
    print("  --update-all           全部更新模式，刷新所有现有记录的Twitter数据")
    print("  --priority-new         优先级模式，专门处理从未同步过的数据")
    print("  --help, -h             显示此帮助信息")
    print()
    print("示例:")
    print("  python sync_campaign_data.py --dry-run")
    print("  python sync_campaign_data.py --update-all --dry-run")
    print("  python sync_campaign_data.py --priority-new")
    print("  python sync_campaign_data.py --priority-new --dry-run")
    print("  python sync_campaign_data.py")

if __name__ == "__main__":
    if '--help' in sys.argv or '-h' in sys.argv:
        show_help()
    else:
        asyncio.run(main())
