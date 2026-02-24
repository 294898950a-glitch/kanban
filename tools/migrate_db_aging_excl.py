import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from pathlib import Path

# 与 database.py 中保持一致：项目根/data/matetial_monitor.db
BASE_DIR = Path(__file__).parent.parent
db_path = str(BASE_DIR / "data" / "matetial_monitor.db")

print(f"[MIGRATE_AGING] 数据库路径: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE kpi_history ADD COLUMN avg_aging_hours_excl REAL DEFAULT 0.0;")
    conn.commit()
    print("[MIGRATE_AGING] ✅ kpi_history.avg_aging_hours_excl 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE_AGING] ℹ️  kpi_history.avg_aging_hours_excl 列已存在，跳过")
    else:
        print(f"[MIGRATE_AGING] ❌ 错误: {e}")

conn.close()
print("[MIGRATE_AGING] 迁移完成")
