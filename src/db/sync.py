import json
from datetime import datetime, timedelta
from src.db.database import SessionLocal
from src.db.models import KPIHistory, AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot
from src.analysis.build_report import run as build_report_run

def safe_float(val):
    try:
        if val == "":
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def safe_str(val):
    if val is None:
        return ""
    return str(val)

def save_to_db(alert_rows, issue_rows, quality_stats, session, batch_id):
    print("\n[DB] 开始将数据写入数据库快照表...")
    ts = datetime.now()
    
    # 计算平均库龄（此段逻辑已经不相关）
    active_hours = []
    now = datetime.now()
    for r in alert_rows:
        rt = safe_str(r.get("接收时间"))
        if rt:
            try:
                fmt_rt = rt.replace("/", "-")
                if len(fmt_rt) > 19: fmt_rt = fmt_rt[:19]
                dt = datetime.strptime(fmt_rt, "%Y-%m-%d %H:%M:%S")
                active_hours.append((now - dt).total_seconds() / 3600.0)
            except Exception:
                pass
    avg_aging = round(sum(active_hours) / len(active_hours), 1) if active_hours else 0.0

    # 1. 写入 KPI
    kpi = KPIHistory(
        batch_id=batch_id,
        timestamp=ts,
        alert_group_count=len(alert_rows),
        high_risk_count=len([
            r for r in alert_rows 
            if safe_float(r.get("偏差(实际-理论)")) > 0.01 
            and not r.get("is_legacy", False)
        ]),
        over_issue_lines=len([r for r in issue_rows if safe_float(r.get("超发量")) > 0.01]) if issue_rows else 0,
        avg_aging_hours=quality_stats.get("avg_aging_hours_current", 0.0),
        avg_aging_hours_excl=quality_stats.get("avg_aging_hours_excl", 0.0),
        confirmed_alert_count=quality_stats.get("confirmed_alert_count", 0),
        unmatched_current_count=quality_stats.get("unmatched_current_count", 0),
        legacy_count=quality_stats.get("legacy_count", 0),
        confirmed_alert_count_excl=quality_stats.get("confirmed_alert_count_excl", 0),
    )
    session.add(kpi)

    # 2. 写入 Alert 离场预警
    if alert_rows:
        alert_inserts = []
        for r in alert_rows:
            alert_inserts.append(AlertReportSnapshot(
                batch_id=batch_id,
                timestamp=ts,
                shop_order=safe_str(r.get("工单号")),
                material_code=safe_str(r.get("物料编号")),
                material_desc=safe_str(r.get("物料描述")),
                warehouse=safe_str(r.get("线边仓")),
                unit=safe_str(r.get("单位")),
                actual_inventory=safe_float(r.get("实际库存(合计)")),
                barcode_count=int(safe_float(r.get("条码数"))),
                order_status=safe_str(r.get("工单状态")),
                planned_qty=safe_float(r.get("计划数量")),
                done_qty=safe_float(r.get("完工数量")),
                bom_unit_qty=safe_float(r.get("BOM单件用量")),
                bom_total_req=safe_float(r.get("BOM总需求量")),
                theory_remain=safe_float(r.get("理论余料")),
                deviation=safe_float(r.get("偏差(实际-理论)")),
                receive_time=safe_str(r.get("接收时间")),
                last_issue_time=safe_str(r.get("最新发料时间")),
                is_legacy=1 if r.get("is_legacy") else 0,
                barcode_list=json.dumps(r.get("barcode_list", []), ensure_ascii=False),
            ))
        session.bulk_save_objects(alert_inserts)

    # 3. 写入 Issue 进场超发
    if issue_rows:
        issue_inserts = []
        for r in issue_rows:
            issue_inserts.append(IssueAuditSnapshot(
                batch_id=batch_id,
                timestamp=ts,
                instruction_doc_id=safe_str(r.get("备料单ID")),
                demand_list_number=safe_str(r.get("备料单号")),
                doc_status=safe_str(r.get("备料单状态")),
                related_wo=safe_str(r.get("关联工单")),
                material_code=safe_str(r.get("物料编号")),
                demand_qty=safe_float(r.get("计划发料量(demandQty)")),
                actual_qty=safe_float(r.get("实际发料量(actualQty)")),
                over_issue_qty=safe_float(r.get("超发量")),
                over_issue_rate=safe_float(r.get("超发率(%)")),
                is_over_issue=safe_str(r.get("是否超发")),
                production_line=safe_str(r.get("产线")),
                warehouse=safe_str(r.get("仓库")),
                bom_demand_qty=safe_float(r.get("BOM标准需求量(sumQty)")),
                over_vs_bom_qty=safe_float(r.get("超发量(vs BOM)")),
                over_vs_bom_rate=safe_float(r.get("超发率%(vs BOM)")),
                plan_issue_date=safe_str(r.get("计划发料日期")),
            ))
        session.bulk_save_objects(issue_inserts)

    # 4. 写入数据质量快照
    from src.db.models import DataQualitySnapshot
    dq = DataQualitySnapshot(
        batch_id=batch_id,
        timestamp=ts,
        inventory_total=quality_stats.get("inventory_total", 0),
        inventory_legacy=quality_stats.get("inventory_legacy", 0),
        inventory_current=quality_stats.get("inventory_current", 0),
        orders_total=quality_stats.get("orders_total", 0),
        alert_matched=quality_stats.get("alert_matched", 0),
        alert_unmatched=quality_stats.get("alert_unmatched", 0),
        alert_match_rate=quality_stats.get("alert_match_rate", 0.0),
        nwms_lines_total=quality_stats.get("nwms_lines_total", 0),
        nwms_lines_matched=quality_stats.get("nwms_lines_matched", 0),
        nwms_match_rate=quality_stats.get("nwms_match_rate", 0.0),
    )
    session.add(dq)

    session.commit()
    print(f"  [DB] 快照写入完成，Batch ID: {batch_id}")
    print(f"  [DB] 数据质量快照写入完成")

def purge_old_batches(session, days: int = 30):
    """删除 N 天前的快照数据，控制 DB 体积"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    for Model in [AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot, KPIHistory]:
        deleted = session.query(Model).filter(Model.timestamp < cutoff).delete()
        if deleted:
            print(f"  [PURGE] {Model.__tablename__}: 删除 {deleted} 条过期记录")
    session.commit()

def run_and_sync():
    """执行生成报告并同步至数据库，同步后清理 30 天前数据"""
    print("[SYNC] 执行原分析逻辑并获取数据...")
    alert_rows, issue_rows, quality_stats = build_report_run()
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    db = SessionLocal()
    try:
        save_to_db(alert_rows, issue_rows, quality_stats, db, batch_id)
        purge_old_batches(db)
    finally:
        db.close()

if __name__ == "__main__":
    run_and_sync()
