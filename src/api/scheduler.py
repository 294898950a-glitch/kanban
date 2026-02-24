from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from src.db.sync import run_and_sync
from src.scrapers.inventory_scraper import run as run_inventory
from src.scrapers.shop_order_scraper import run as run_shop_order
from src.scrapers.nwms_scraper import run as run_nwms
from src.scrapers.bom_scraper import run as run_bom

# 日志打印
def log(msg: str):
    print(f"[Scheduler] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

def run_inventory_and_orders():
    """整点同步：库存 + 工单 + NWMS 发料明细 + 分析"""
    log("开始执行整点同步 (库存+工单+NWMS+分析)...")
    try:
        run_inventory()
        run_shop_order(start_date="2026-01-01 00:00:00")
        run_nwms(start_date="2026-01-01")
        run_and_sync()
        log("整点同步完毕！")
    except Exception as e:
        log(f"整点同步执行失败: {e}")

def run_nwms_full_sync():
    """重负载全量同步：深夜拉取 BOM + NWMS 扫码明细"""
    log("开始执行全量 NWMS 数据同步...")
    try:
        run_bom()
        run_nwms(start_date="2026-01-01")
        run_and_sync()
        log("全量 NWMS 审计分析完毕！")
    except Exception as e:
        log(f"全量同步执行失败: {e}")

# 初始化调度器
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

def start_scheduler():
    # 每小时整点同步（全天，覆盖中国+墨西哥双时区工作时段）
    # TZ=Asia/Shanghai 已设置，hour 按 CST 解释
    scheduler.add_job(
        run_inventory_and_orders,
        trigger=CronTrigger(minute=0),   # 每小时，不限时段
        id="hourly_sync",
        name="每小时库存状态同步",
        replace_existing=True
    )

    # 每天 02:00 CST（墨西哥时间 12:00 前一天）触发深度 NWMS 全量抓取
    scheduler.add_job(
        run_nwms_full_sync,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_full_sync",
        name="凌晨全量发料审计同步",
        replace_existing=True
    )

    scheduler.start()
    log("定时调度器已启动")
