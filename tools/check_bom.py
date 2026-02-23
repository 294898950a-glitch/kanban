import sqlite3
conn = sqlite3.connect("data/matetial_monitor.db")
c = conn.cursor()
c.execute("""
    SELECT material_code, demand_qty, actual_qty, over_issue_qty,
           bom_demand_qty, over_vs_bom_qty, over_vs_bom_rate
    FROM issue_audit_snapshots
    WHERE batch_id='20260223_122241' AND bom_demand_qty > 0
    ORDER BY over_vs_bom_qty DESC
    LIMIT 5
""")
rows = c.fetchall()
print(f"{'物料编号':15} {'NWMS计划':>10} {'实发':>10} {'超发(NWMS)':>12} {'BOM需求':>10} {'超发(BOM)':>10} {'超发率%(BOM)':>12}")
print("-" * 80)
for r in rows:
    print(f"{r[0]:15} {r[1]:>10.0f} {r[2]:>10.0f} {r[3]:>12.0f} {r[4]:>10.0f} {r[5]:>10.0f} {r[6]:>12.1f}%")
conn.close()
