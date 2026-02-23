"""
端对端一致性验证脚本
比较数据源（SQLite 直查）与前端 API 返回数据是否一致

使用方式：
  # 需先启动后端服务：
  # venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
  
  export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
  venv/bin/python3 test_consistency.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import sqlite3
import urllib.request
from pathlib import Path

API_BASE = "http://localhost:8000"
DB_PATH = str(Path("data/matetial_monitor.db"))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⚠️ SKIP"

def api_get(path):
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"__error__": str(e)}

def db_query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    return passed

def run_tests():
    results = []
    print("=" * 60)
    print("LMT-Kanban 端对端一致性验证")
    print("=" * 60)

    # ── 1. KPI Summary ──
    print("\n【1】KPI 汇总 (/api/kpi/summary)")
    api_kpi = api_get("/api/kpi/summary")
    if "__error__" in api_kpi:
        print(f"  {SKIP}  后端未启动或无法连接: {api_kpi['__error__']}")
        results.append(None)
    else:
        batch_id = api_kpi.get("batch_id")
        db_kpi = db_query(
            "SELECT * FROM kpi_history WHERE batch_id=? ORDER BY timestamp DESC LIMIT 1",
            (batch_id,)
        )
        if not db_kpi:
            results.append(check("batch_id 在数据库中存在", False, f"batch_id={batch_id} 找不到"))
        else:
            dk = db_kpi[0]
            results.append(check(
                "alert_group_count 一致",
                api_kpi["alert_group_count"] == dk["alert_group_count"],
                f"API={api_kpi['alert_group_count']}  DB={dk['alert_group_count']}"
            ))
            results.append(check(
                "high_risk_count 一致",
                api_kpi["high_risk_count"] == dk["high_risk_count"],
                f"API={api_kpi['high_risk_count']}  DB={dk['high_risk_count']}"
            ))
            results.append(check(
                "over_issue_lines 一致",
                api_kpi["over_issue_lines"] == dk["over_issue_lines"],
                f"API={api_kpi['over_issue_lines']}  DB={dk['over_issue_lines']}"
            ))
            results.append(check(
                "avg_aging_hours 一致",
                abs(api_kpi["avg_aging_hours"] - dk["avg_aging_hours"]) < 0.1,
                f"API={api_kpi['avg_aging_hours']}  DB={dk['avg_aging_hours']}"
            ))

    # ── 2. Alerts Top10 ──
    print("\n【2】退料预警 Top10 (/api/alerts/top10)")
    api_alerts = api_get("/api/alerts/top10")
    if isinstance(api_alerts, dict) and "__error__" in api_alerts:
        print(f"  {SKIP}  后端未启动: {api_alerts['__error__']}")
        results.append(None)
    else:
        # 直接从最新批次查询
        latest_batch = db_query(
            "SELECT batch_id FROM kpi_history ORDER BY timestamp DESC LIMIT 1"
        )
        if latest_batch:
            bid = latest_batch[0]["batch_id"]
            # Phase3: 按 actual_inventory DESC，完工 + 非历史遗留，最多10条
            db_top10 = db_query(
                "SELECT * FROM alert_report_snapshots WHERE batch_id=? AND is_legacy=0 "
                "AND order_status IN ('Completado','完成','Completed','已完成','Se ha iniciado la construcción') "
                "ORDER BY actual_inventory DESC LIMIT 10",
                (bid,)
            )
            results.append(check(
                "Top10 条目数一致",
                len(api_alerts) == len(db_top10),
                f"API={len(api_alerts)}条  DB={len(db_top10)}条"
            ))
            if api_alerts and db_top10:
                results.append(check(
                    "Top1 工单号一致",
                    api_alerts[0]["shop_order"] == db_top10[0]["shop_order"],
                    f"API={api_alerts[0]['shop_order']}  DB={db_top10[0]['shop_order']}"
                ))
                results.append(check(
                    "Top1 实际库存量一致",
                    abs(float(api_alerts[0]["actual_inventory"]) - float(db_top10[0]["actual_inventory"])) < 0.01,
                    f"API={api_alerts[0]['actual_inventory']}  DB={db_top10[0]['actual_inventory']}"
                ))

    # ── 3. Issues Top5 ──
    print("\n【3】超发预警 Top5 (/api/issues/top5)")
    api_issues = api_get("/api/issues/top5")
    if isinstance(api_issues, dict) and "__error__" in api_issues:
        print(f"  {SKIP}  后端未启动: {api_issues['__error__']}")
        results.append(None)
    else:
        latest_batch = db_query(
            "SELECT batch_id FROM kpi_history ORDER BY timestamp DESC LIMIT 1"
        )
        if latest_batch:
            bid = latest_batch[0]["batch_id"]
            db_top5 = db_query(
                "SELECT * FROM issue_audit_snapshots WHERE batch_id=? AND over_issue_qty > 0.01 "
                "ORDER BY over_issue_qty DESC LIMIT 5",
                (bid,)
            )
            results.append(check(
                "Top5 条目数一致",
                len(api_issues) == len(db_top5),
                f"API={len(api_issues)}条  DB={len(db_top5)}条"
            ))
            if api_issues and db_top5:
                results.append(check(
                    "Top1 物料编号一致",
                    api_issues[0]["material_code"] == db_top5[0]["material_code"],
                    f"API={api_issues[0]['material_code']}  DB={db_top5[0]['material_code']}"
                ))

    # ── 4. 批次列表 ──
    print("\n【4】批次列表 (/api/batches)")
    api_batches = api_get("/api/batches")
    if isinstance(api_batches, dict) and "__error__" in api_batches:
        print(f"  {SKIP}  后端未启动: {api_batches['__error__']}")
        results.append(None)
    else:
        db_batches = db_query(
            "SELECT DISTINCT batch_id FROM kpi_history ORDER BY batch_id DESC"
        )
        api_ids = [b["batch_id"] for b in api_batches] if isinstance(api_batches, list) else []
        db_ids = [b["batch_id"] for b in db_batches]
        results.append(check(
            "批次数量一致",
            len(api_ids) == len(db_ids),
            f"API={len(api_ids)}个  DB={len(db_ids)}个"
        ))
        if api_ids and db_ids:
            results.append(check(
                "最新批次一致",
                api_ids[0] == db_ids[0],
                f"API={api_ids[0]}  DB={db_ids[0]}"
            ))

    # ── 5. 数据质量快照 ──
    print("\n【5】数据质量快照（直接查库）")
    dq = db_query(
        "SELECT * FROM data_quality_snapshots ORDER BY timestamp DESC LIMIT 1"
    )
    if dq:
        d = dq[0]
        print(f"  最新批次: {d['batch_id']}")
        print(f"  库存总量: {d['inventory_total']}  历史遗留: {d['inventory_legacy']}  当期: {d['inventory_current']}")
        print(f"  工单匹配率: {d['alert_match_rate']}%  NWMS匹配率: {d['nwms_match_rate']}%")
        results.append(check(
            "历史遗留比例合理（< 30%）",
            d['inventory_legacy'] / max(d['inventory_total'], 1) < 0.3,
            f"遗留占比={(d['inventory_legacy']/max(d['inventory_total'],1)*100):.1f}%"
        ))
    else:
        print(f"  {SKIP}  data_quality_snapshots 无记录")

    # ── 汇总 ──
    print("\n" + "=" * 60)
    valid = [r for r in results if r is not None]
    skipped = results.count(None)
    passed = sum(1 for r in valid if r)
    failed = sum(1 for r in valid if not r)
    print(f"总计: {passed} 通过  {failed} 失败  {skipped} 跳过（后端未启动）")
    if failed == 0 and passed > 0:
        print("🎉 所有校验通过，数据源与前端数据完全一致！")
    elif failed > 0:
        print("⚠️  存在不一致，请检查上述失败项")

if __name__ == "__main__":
    run_tests()
