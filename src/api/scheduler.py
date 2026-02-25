from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import threading

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

def _last_scheduled_time(now: datetime) -> datetime:
    """返回当前时间之前最近一个应触发的调度时刻（06/10/14/18/22 CST）"""
    scheduled_hours = [6, 10, 14, 18, 22]
    past = [h for h in scheduled_hours if h <= now.hour]
    if past:
        return now.replace(hour=max(past), minute=0, second=0, microsecond=0)
    # 还没到今天06:00，取昨天22:00
    return (now - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)


def check_and_catchup():
    """启动时检测是否跳过同步，若跳过则异步补跑一次"""
    from src.db.database import SessionLocal
    from src.db.models import KPIHistory
    from sqlalchemy import select, desc

    db = SessionLocal()
    try:
        latest = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
    finally:
        db.close()

    if latest is None:
        log("首次启动，无历史数据，跳过补跑检查")
        return

    now = datetime.now()
    last_sync = latest.timestamp
    last_scheduled = _last_scheduled_time(now)

    if last_sync < last_scheduled:
        log(f"[补跑] 检测到跳过同步：上次={last_sync.strftime('%m-%d %H:%M')}，"
            f"应在 {last_scheduled.strftime('%m-%d %H:%M')} 同步，立即补跑...")
        threading.Thread(target=run_inventory_and_orders, daemon=True, name="catchup").start()
    else:
        log(f"无需补跑，上次同步={last_sync.strftime('%m-%d %H:%M')}")


# 初始化调度器
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

def start_scheduler():
    # 06:00 晨间全量同步（含 BOM 刷新）
    scheduler.add_job(
        run_morning_full_sync,
        trigger=CronTrigger(hour=6, minute=0),
        id="morning_full_sync",
        name="晨间全量同步（含BOM）",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 10/14/18/22 每4小时同步（不含 BOM，工作时段覆盖 CST + 蒙特雷时区）
    scheduler.add_job(
        run_inventory_and_orders,
        trigger=CronTrigger(hour="10,14,18,22", minute=0),
        id="quad_hourly_sync",
        name="每4小时库存状态同步",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    log("定时调度器已启动（06/10/14/18/22 CST，晨间含BOM全量）")
    check_and_catchup()
