from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from typing import List, Optional
from datetime import datetime
import json

from src.config.common_materials import COMMON_MATERIALS
from src.db.database import get_db, SessionLocal
from src.db.models import KPIHistory, AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot, InventoryStatusSnapshot
from src.api.scheduler import start_scheduler
from contextlib import asynccontextmanager

def calculate_aging_days(receive_time_str) -> float:
    if not receive_time_str:
        return -1.0
    try:
        s = str(receive_time_str).strip().split(" ")[0].replace("/", "-")
        parts = s.split("-")
        if len(parts) == 3:
            s = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        return round((datetime.utcnow() - datetime.strptime(s, "%Y-%m-%d")).total_seconds() / 86400, 1)
    except Exception:
        return -1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动定时任务
    start_scheduler()
    yield
    # 关闭时可在这里清理资源

# 初始化 FastAPI
app = FastAPI(title="LMT-Kanban API", version="1.0.0", lifespan=lifespan)


# 配置跨域，供大屏分离部署
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/kpi/summary")
def get_kpi_summary(exclude_common: bool = False):
    """获取最新批次的全局 KPI 汇总"""
    db = SessionLocal()
    try:
        # 获取最新的一条 KPI 记录
        latest_kpi = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        
        if not latest_kpi:
            return {"error": "暂无数据"}

        return {
            "batch_id": latest_kpi.batch_id,
            "timestamp": latest_kpi.timestamp.isoformat(),
            "alert_group_count": latest_kpi.alert_group_count,
            "high_risk_count": latest_kpi.high_risk_count,
            "over_issue_lines": latest_kpi.over_issue_lines,
            "avg_aging_hours": (latest_kpi.avg_aging_hours_excl or 0.0) if exclude_common else (latest_kpi.avg_aging_hours or 0.0),
            "confirmed_alert_count": (latest_kpi.confirmed_alert_count_excl or 0) if exclude_common else (latest_kpi.confirmed_alert_count or 0),
            "unmatched_current_count": latest_kpi.unmatched_current_count or 0,
            "legacy_count": latest_kpi.legacy_count or 0,
        }
    finally:
        db.close()

@app.get("/api/kpi/trend")
def get_kpi_trend(limit: int = 14, exclude_common: bool = False):
    """获取最近若干次的 KPI 趋势，用于绘制折线图"""
    db = SessionLocal()
    try:
        history = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(limit)
        ).scalars().all()
        
        # 将最新的倒序翻转为时间正序
        history.reverse()
        
        return [
            {
                "timestamp": h.timestamp.strftime("%m-%d %H:%M"),
                "alert_group_count": h.alert_group_count,
                "high_risk_count": h.high_risk_count,
                "confirmed_alert_count": (h.confirmed_alert_count_excl or 0) if exclude_common else (h.confirmed_alert_count or 0),
                "over_issue_lines": h.over_issue_lines,
                "avg_aging_hours": (h.avg_aging_hours_excl or 0.0) if exclude_common else (h.avg_aging_hours or 0.0),
            }
            for h in history
        ]
    finally:
        db.close()

@app.get("/api/kpi/aging-distribution")
def get_aging_distribution(exclude_common: bool = False):
    """返回最新批次当期已核实物料的库龄分布"""
    db = SessionLocal()
    try:
        latest = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        if not latest:
            return {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}

        stmt = select(AlertReportSnapshot) \
            .where(AlertReportSnapshot.batch_id == latest.batch_id) \
            .where(AlertReportSnapshot.is_legacy == 0)

        if exclude_common:
            stmt = stmt.where(AlertReportSnapshot.material_code.not_in(list(COMMON_MATERIALS)))

        rows = db.execute(stmt).scalars().all()

        dist = {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}
        for r in rows:
            days = calculate_aging_days(r.receive_time)
            if days < 0: continue
            if days <= 1:    dist["le1"]    += 1
            elif days <= 3:  dist["d1_3"]   += 1
            elif days <= 7:  dist["d3_7"]   += 1
            elif days <= 14: dist["d7_14"]  += 1
            elif days <= 30: dist["d14_30"] += 1
            else:            dist["gt30"]   += 1
        return dist
    finally:
        db.close()

COMPLETED_STATUSES = {'Completado', '完成', 'Completed', '已完成'}

@app.get("/api/alerts/top10")
def get_alerts_top10(exclude_common: bool = False):
    """当期退料预警：已完工且仍有库存，按实际库存量排序"""
    db = SessionLocal()
    try:
        latest_kpi = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        
        if not latest_kpi:
            return []

        stmt = select(AlertReportSnapshot) \
            .where(AlertReportSnapshot.batch_id == latest_kpi.batch_id) \
            .where(AlertReportSnapshot.is_legacy == 0) \
            .where(AlertReportSnapshot.order_status.in_(COMPLETED_STATUSES))
        if exclude_common:
            stmt = stmt.where(AlertReportSnapshot.material_code.not_in(list(COMMON_MATERIALS)))
        stmt = stmt.order_by(desc(AlertReportSnapshot.actual_inventory))
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "shop_order": r.shop_order,
                "material_code": r.material_code,
                "material_desc": r.material_desc,
                "warehouse": r.warehouse,
                "actual_inventory": r.actual_inventory,
                "unit": r.unit,
                "barcode_count": r.barcode_count,
                "aging_days": calculate_aging_days(r.receive_time),
                "reuse_label": r.reuse_label or "",
            }
            for r in rows
        ]
    finally:
        db.close()

@app.get("/api/issues/top5")
def get_issues_top5():
    """获取最新批次中最严重的前 5 个超发记录"""
    db = SessionLocal()
    try:
        latest_kpi = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        
        if not latest_kpi:
            return []

        rows = db.execute(
            select(IssueAuditSnapshot)
            .where(IssueAuditSnapshot.batch_id == latest_kpi.batch_id)
            .where(IssueAuditSnapshot.over_issue_qty > 0.01)
            .order_by(desc(IssueAuditSnapshot.over_issue_qty))
        ).scalars().all()

        return [
            {
                "material_code": t.material_code,
                "production_line": t.production_line,
                "related_wo": t.related_wo,
                "plan_issue_date": t.plan_issue_date or "",
                "demand_qty": t.demand_qty,
                "actual_qty": t.actual_qty,
                "over_issue_qty": t.over_issue_qty,
                "over_issue_rate": t.over_issue_rate,
                "bom_demand_qty": t.bom_demand_qty,
                "over_vs_bom_rate": t.over_vs_bom_rate,
            }
            for t in rows
        ]
    finally:
        db.close()

@app.get("/api/batches")
def get_batches():
    """返回所有历史批次列表（降序）"""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(KPIHistory.batch_id, KPIHistory.timestamp)
            .order_by(desc(KPIHistory.timestamp))
        ).all()
        return [{"batch_id": r.batch_id, "timestamp": r.timestamp.isoformat()} for r in rows]
    finally:
        db.close()

@app.get("/api/alerts/list")
def get_alerts_list(batch_id: str = "", q: str = "", exclude_common: bool = False):
    """离场审计完整明细，支持关键字过滤（工单号或物料编号）"""
    db = SessionLocal()
    try:
        # 未指定批次时取最新批次
        if not batch_id:
            latest = db.execute(
                select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
            ).scalar_one_or_none()
            if not latest:
                return []
            batch_id = latest.batch_id

        stmt = select(AlertReportSnapshot).where(AlertReportSnapshot.batch_id == batch_id)
        if q:
            stmt = stmt.where(
                AlertReportSnapshot.shop_order.contains(q) |
                AlertReportSnapshot.material_code.contains(q) |
                AlertReportSnapshot.barcode_list.contains(q)
            )
        if exclude_common:
            stmt = stmt.where(AlertReportSnapshot.material_code.not_in(list(COMMON_MATERIALS)))
        stmt = stmt.order_by(desc(AlertReportSnapshot.deviation))
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "shop_order": r.shop_order,
                "material_code": r.material_code,
                "material_desc": r.material_desc,
                "warehouse": r.warehouse,
                "actual_inventory": r.actual_inventory,
                "unit": r.unit,
                "barcode_count": r.barcode_count,
                "barcode_list": json.loads(r.barcode_list or "[]"),
                "aging_days": calculate_aging_days(r.receive_time),
                "theory_remain": r.theory_remain,
                "deviation": r.deviation,
                "reuse_label": r.reuse_label or "",
            }
            for r in rows
        ]
    finally:
        db.close()

@app.get("/api/issues/list")
def get_issues_list(batch_id: str = "", q: str = ""):
    """进场审计完整明细，支持关键字过滤（物料编号或备料单号）"""
    db = SessionLocal()
    try:
        if not batch_id:
            latest = db.execute(
                select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
            ).scalar_one_or_none()
            if not latest:
                return []
            batch_id = latest.batch_id

        stmt = select(IssueAuditSnapshot).where(IssueAuditSnapshot.batch_id == batch_id)
        if q:
            stmt = stmt.where(
                IssueAuditSnapshot.material_code.contains(q) |
                IssueAuditSnapshot.demand_list_number.contains(q)
            )
        stmt = stmt.order_by(desc(IssueAuditSnapshot.over_issue_qty))
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "demand_list_number": r.demand_list_number,
                "material_code": r.material_code,
                "related_wo": r.related_wo,
                "production_line": r.production_line,
                "plan_issue_date": r.plan_issue_date or "",
                "demand_qty": r.demand_qty,
                "actual_qty": r.actual_qty,
                "over_issue_qty": r.over_issue_qty,
                "over_issue_rate": r.over_issue_rate,
                "bom_demand_qty": r.bom_demand_qty,
                "over_vs_bom_rate": r.over_vs_bom_rate,
            }
            for r in rows
        ]
    finally:
        db.close()

@app.get("/api/inventory/status")
def get_inventory_status(batch_id: str = "", q: str = "", label: str = "", exclude_common: bool = False):
    """
    全量线边仓物料状态快照（Phase 8）
    label 过滤：current / upcoming / completed / reuse_current / reuse_upcoming / 空=全部
    """
    db = SessionLocal()
    try:
        if not batch_id:
            latest = db.execute(
                select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
            ).scalar_one_or_none()
            if not latest:
                return []
            batch_id = latest.batch_id

        stmt = select(InventoryStatusSnapshot).where(
            InventoryStatusSnapshot.batch_id == batch_id
        )
        if q:
            stmt = stmt.where(
                InventoryStatusSnapshot.shop_order.contains(q) |
                InventoryStatusSnapshot.material_code.contains(q) |
                InventoryStatusSnapshot.barcode_list.contains(q)
            )
        if label in ("current", "upcoming", "completed"):
            stmt = stmt.where(InventoryStatusSnapshot.wo_status_label == label)
        elif label in ("reuse_current", "reuse_upcoming"):
            stmt = stmt.where(InventoryStatusSnapshot.reuse_label == label)

        if exclude_common:
            stmt = stmt.where(InventoryStatusSnapshot.material_code.not_in(list(COMMON_MATERIALS)))

        stmt = stmt.order_by(
            InventoryStatusSnapshot.wo_status_label,
            desc(InventoryStatusSnapshot.actual_inventory)
        )
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "shop_order":       r.shop_order,
                "material_code":    r.material_code,
                "material_desc":    r.material_desc,
                "warehouse":        r.warehouse,
                "unit":             r.unit,
                "actual_inventory": r.actual_inventory,
                "barcode_count":    r.barcode_count,
                "barcode_list":     json.loads(r.barcode_list or "[]"),
                "order_status":     r.order_status,
                "wo_status_label":  r.wo_status_label or "",
                "aging_days":       calculate_aging_days(r.receive_time),
                "is_legacy":        r.is_legacy,
                "reuse_label":      r.reuse_label or "",
                "theory_remain":    r.theory_remain,
                "deviation":        r.deviation,
            }
            for r in rows
        ]
    finally:
        db.close()

