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
    """4小时同步：库存 + 工单 + NWMS 发料明细 + 分析"""
    log("开始执行定时同步 (库存+工单+NWMS+分析)...")
    try:
        run_inventory()
        run_shop_order(start_date="2026-01-01 00:00:00")
        run_nwms(start_date="2026-01-01")
        run_and_sync()
        log("定时同步完毕！")
    except Exception as e:
        log(f"定时同步执行失败: {e}")

def run_morning_full_sync():
    """06:00 晨间全量同步：BOM + 库存 + 工单 + NWMS + 分析"""
    log("开始执行晨间全量同步 (BOM+库存+工单+NWMS+分析)...")
    try:
        run_bom()
        run_inventory()
        run_shop_order(start_date="2026-01-01 00:00:00")
        run_nwms(start_date="2026-01-01")
        run_and_sync()
        log("晨间全量同步完毕！")
    except Exception as e:
        log(f"晨间全量同步执行失败: {e}")

# 初始化调度器
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

def start_scheduler():
    # 06:00 晨间全量同步（含 BOM 刷新）
    scheduler.add_job(
        run_morning_full_sync,
        trigger=CronTrigger(hour=6, minute=0),
        id="morning_full_sync",
        name="晨间全量同步（含BOM）",
        replace_existing=True
    )

    # 10/14/18/22 每4小时同步（不含 BOM，工作时段覆盖 CST + 蒙特雷时区）
    scheduler.add_job(
        run_inventory_and_orders,
        trigger=CronTrigger(hour="10,14,18,22", minute=0),
        id="quad_hourly_sync",
        name="每4小时库存状态同步",
        replace_existing=True
    )

    scheduler.start()
    log("定时调度器已启动（06/10/14/18/22 CST，晨间含BOM全量）")
