import sqlite3
conn = sqlite3.connect("data/matetial_monitor.db")
c = conn.cursor()
c.execute("SELECT batch_id, inventory_total, inventory_legacy, alert_match_rate, nwms_match_rate FROM data_quality_snapshots ORDER BY timestamp DESC LIMIT 3")
rows = c.fetchall()
for r in rows:
    print(r)
conn.close()
