import os, sys
sys.path.insert(0, os.path.abspath('.'))

from src.db.database import SessionLocal
from src.db.models import KPIHistory, AlertReportSnapshot
from sqlalchemy import desc

db = SessionLocal()
kpis = db.query(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(5).all()
for k in kpis:
    print(f"ID={k.id}, timestamp={k.timestamp}, batch_id={k.batch_id}, confirmed={k.confirmed_alert_count}, excl={k.confirmed_alert_count_excl}")

latest_batch = kpis[0].batch_id
print(f"Latest batch: {latest_batch}")

# test api locally
from src.api.main import get_kpi_summary, get_alerts_list
print(f"kpi_summary(False): {get_kpi_summary(False)}")
print(f"kpi_summary(True): {get_kpi_summary(True)}")

alerts_false = get_alerts_list(latest_batch, "", False)
alerts_true = get_alerts_list(latest_batch, "", True)
print(f"alerts(False) count: {len(alerts_false)}")
print(f"alerts(True) count: {len(alerts_true)}")
