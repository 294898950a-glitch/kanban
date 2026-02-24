from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import subprocess
import os

import sys
from src.db.sync import run_and_sync
# 项目根目录：src/api/scheduler.py → src/api → src → 项目根
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 使用当前进程的 Python 解释器（兼容 venv 和 Docker）
PYTHON = sys.executable

# 日志打印
def log(msg: str):
    print(f"[Scheduler] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

def run_inventory_and_orders():
    """整点同步：库存 + 工单 + NWMS 发料明细 + 分析"""
    log("开始执行整点同步 (库存+工单+NWMS+分析)...")
    try:
        subprocess.run([PYTHON, "src/scrapers/inventory_scraper.py"], cwd=BASE_DIR, check=True)
        subprocess.run([
            PYTHON, "src/scrapers/shop_order_scraper.py",
            "--start", "2026-01-01 00:00:00"
        ], cwd=BASE_DIR, check=True)
        subprocess.run([
            PYTHON, "src/scrapers/nwms_scraper.py",
            "--start", "2026-01-01"
        ], cwd=BASE_DIR, check=True)
        run_and_sync()
        log("整点同步完毕！")
    except Exception as e:
        log(f"整点同步执行失败: {e}")

def run_nwms_full_sync():
    """重负载全量同步：深夜拉取 NWMS 扫码明细"""
    log("开始执行全量 NWMS 数据同步...")
    try:
        subprocess.run([PYTHON, "src/scrapers/bom_scraper.py"], cwd=BASE_DIR)

        # 只拉取 2026-01-01 以后的备料单，避免全量历史数据
        subprocess.run([PYTHON, "src/scrapers/nwms_scraper.py", "--start", "2026-01-01"], cwd=BASE_DIR)
        
        # 跑完再次生成审计并同步
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
