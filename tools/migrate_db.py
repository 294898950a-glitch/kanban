import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from pathlib import Path

# 与 database.py 中保持一致：项目根/data/matetial_monitor.db
BASE_DIR = Path(__file__).parent.parent  # tools/ → 项目根
db_path = str(BASE_DIR / "data" / "matetial_monitor.db")

print(f"[MIGRATE] 数据库路径: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. 给 alert_report_snapshots 表加 is_legacy 列
try:
    cursor.execute("ALTER TABLE alert_report_snapshots ADD COLUMN is_legacy INTEGER DEFAULT 0;")
    conn.commit()
    print("[MIGRATE] ✅ alert_report_snapshots.is_legacy 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  alert_report_snapshots.is_legacy 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# 2. 新建 data_quality_snapshots 表
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_quality_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id VARCHAR(50) NOT NULL,
            timestamp DATETIME,
            inventory_total INTEGER DEFAULT 0,
            inventory_legacy INTEGER DEFAULT 0,
            inventory_current INTEGER DEFAULT 0,
            orders_total INTEGER DEFAULT 0,
            alert_matched INTEGER DEFAULT 0,
            alert_unmatched INTEGER DEFAULT 0,
            alert_match_rate REAL DEFAULT 0.0,
            nwms_lines_total INTEGER DEFAULT 0,
            nwms_lines_matched INTEGER DEFAULT 0,
            nwms_match_rate REAL DEFAULT 0.0
        );
    """)
    conn.commit()
    print("[MIGRATE] ✅ data_quality_snapshots 表已就绪")
except sqlite3.OperationalError as e:
    print(f"[MIGRATE] ❌ 错误: {e}")

# 3. 给 issue_audit_snapshots 表加 BOM 对比列
for col, coltype in [
    ("bom_demand_qty",  "REAL DEFAULT 0.0"),
    ("over_vs_bom_qty", "REAL DEFAULT 0.0"),
    ("over_vs_bom_rate","REAL DEFAULT 0.0"),
]:
    try:
        cursor.execute(f"ALTER TABLE issue_audit_snapshots ADD COLUMN {col} {coltype};")
        conn.commit()
        print(f"[MIGRATE] ✅ issue_audit_snapshots.{col} 列新增成功")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"[MIGRATE] ℹ️  issue_audit_snapshots.{col} 列已存在，跳过")
        else:
            print(f"[MIGRATE] ❌ 错误: {e}")

# 4. 给 kpi_history 表加 Phase 3 三类计数
for col, coltype in [
    ("confirmed_alert_count",   "INTEGER DEFAULT 0"),
    ("unmatched_current_count", "INTEGER DEFAULT 0"),
    ("legacy_count",            "INTEGER DEFAULT 0"),
]:
    try:
        cursor.execute(f"ALTER TABLE kpi_history ADD COLUMN {col} {coltype};")
        conn.commit()
        print(f"[MIGRATE] ✅ kpi_history.{col} 列新增成功")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"[MIGRATE] ℹ️  kpi_history.{col} 列已存在，跳过")
        else:
            print(f"[MIGRATE] ❌ 错误: {e}")

# 5. 给 alert_report_snapshots 表加 barcode_list 列（KPI 精修）
try:
    cursor.execute("ALTER TABLE alert_report_snapshots ADD COLUMN barcode_list TEXT DEFAULT '[]';")
    conn.commit()
    print("[MIGRATE] ✅ alert_report_snapshots.barcode_list 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  alert_report_snapshots.barcode_list 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# 6. 给 issue_audit_snapshots 表加 plan_issue_date 列
try:
    cursor.execute("ALTER TABLE issue_audit_snapshots ADD COLUMN plan_issue_date VARCHAR(50) DEFAULT '';")
    conn.commit()
    print("[MIGRATE] ✅ issue_audit_snapshots.plan_issue_date 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  issue_audit_snapshots.plan_issue_date 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# 7. 给 kpi_history 表加 confirmed_alert_count_excl 列
try:
    cursor.execute("ALTER TABLE kpi_history ADD COLUMN confirmed_alert_count_excl INTEGER DEFAULT 0;")
    conn.commit()
    print("[MIGRATE] ✅ kpi_history.confirmed_alert_count_excl 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  kpi_history.confirmed_alert_count_excl 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# Phase 8 - Step 1: alert_report_snapshots 新增 reuse_label 列
try:
    cursor.execute("ALTER TABLE alert_report_snapshots ADD COLUMN reuse_label VARCHAR(20) DEFAULT '';")
    conn.commit()
    print("[MIGRATE] ✅ alert_report_snapshots.reuse_label 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  alert_report_snapshots.reuse_label 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# Phase 8 - Step 2: 新建 inventory_status_snapshots 表
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_status_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id VARCHAR(50) NOT NULL,
            timestamp DATETIME,
            shop_order VARCHAR(50),
            material_code VARCHAR(50),
            material_desc TEXT,
            warehouse VARCHAR(100),
            unit VARCHAR(20),
            actual_inventory REAL DEFAULT 0.0,
            barcode_count INTEGER DEFAULT 0,
            order_status VARCHAR(50),
            wo_status_label VARCHAR(20) DEFAULT '',
            receive_time VARCHAR(50),
            is_legacy INTEGER DEFAULT 0,
            barcode_list TEXT DEFAULT '[]',
            reuse_label VARCHAR(20) DEFAULT '',
            theory_remain REAL DEFAULT 0.0,
            deviation REAL DEFAULT 0.0
        );
    """)
    conn.commit()
    print("[MIGRATE] ✅ inventory_status_snapshots 表已就绪")
except sqlite3.OperationalError as e:
    print(f"[MIGRATE] ❌ 错误: {e}")

conn.close()
print("[MIGRATE] 迁移完成")
