import sqlite3

conn = sqlite3.connect("matetial_monitor.db")
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE alert_report_snapshots ADD COLUMN is_legacy INTEGER DEFAULT 0;")
    conn.commit()
    print("Column added successfully.")
except sqlite3.OperationalError as e:
    print(f"OperationalError: {e}")
finally:
    conn.close()
