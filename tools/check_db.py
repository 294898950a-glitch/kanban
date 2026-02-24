import os, sys
sys.path.insert(0, os.path.abspath('.'))

from src.db.database import SessionLocal
from src.db.models import KPIHistory

db = SessionLocal()
k = db.query(KPIHistory).order_by(KPIHistory.id.desc()).first()
print(f"confirmed: {k.confirmed_alert_count}, excl: {k.confirmed_alert_count_excl}")

# count from raw data
import json
import csv
with open('data/raw/alert_report.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

from src.config.common_materials import COMMON_MATERIALS
matched = [r for r in rows if r["物料编号"] in COMMON_MATERIALS]
print(f"Found {len(matched)} matching rows in alert_report.csv")
