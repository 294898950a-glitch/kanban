"""
物料流转双向审计报告生成器

输入（data/raw/）：
  shop_orders_latest.json       — IMES 工单数据
  bom_details_latest.json       — IMES BOM 明细
  inventory_latest.csv          — SSRS 线边仓库存
  nwms_issue_details_latest.json — NWMS 发料行明细（可选，未运行时退化为三表分析）

输出（data/raw/）：
  alert_report.csv              — 退料预警（离场审计）：完工工单仍有线边仓库存
  issue_audit_report.csv        — 超发预警（进场审计）：实际发料 > BOM计划（需NWMS数据）

运行：
  python3 src/analysis/build_report.py
"""

import json
import csv
import io
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from src.config.common_materials import COMMON_MATERIALS

BASE = Path(__file__).parent.parent.parent / "data" / "raw"

COMPLETED_STATUSES = {"Completado", "完成", "Completed", "已完成", "Se ha iniciado la construcción"}


# ═══════════════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_shop_orders():
    path = BASE / "shop_orders_latest.json"
    with open(path, encoding="utf-8") as f:
        orders = json.load(f)
    return {o["shopOrder"]: o for o in orders if o.get("shopOrder")}


def load_bom():
    path = BASE / "bom_details_latest.json"
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    # 索引：(shopOrder, componentGbo) → bom行
    index = {}
    for r in rows:
        key = (r.get("shopOrder", ""), r.get("componentGbo", ""))
        if key[0] and key[1]:
            index[key] = r
    return index


def load_inventory():
    """
    返回两个结构：
    - grouped: (wo, mat) → 汇总数据，用于退料预警分析
    - raw_rows: 原始条码级行列表，用于生成 alert_report_detail.csv
    """
    path = BASE / "inventory_latest.csv"
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    raw_rows = []
    grouped = defaultdict(lambda: {
        "qty": 0.0, "barcodes": 0,
        "desc": "", "warehouse": "", "unit": "",
        "receive_time": "", "issue_time": "",
        "barcode_list": [],
    })
    for r in rows:
        wo = (r.get("指定工单") or "").strip()
        mat = (r.get("物料") or "").strip()
        qty_str = (r.get("现存量") or "0").replace(",", "")
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 0.0
        if not wo or not mat or qty <= 0.01:
            continue
        key = (wo, mat)
        g = grouped[key]
        g["qty"] += qty
        g["barcodes"] += 1
        barcode = r.get("条码", "").strip() or r.get("barcode", "").strip()
        if barcode and barcode not in g["barcode_list"]:
            g["barcode_list"].append(barcode)
        g["desc"] = g["desc"] or r.get("物料描述", "")
        g["warehouse"] = g["warehouse"] or r.get("线边仓描述", r.get("线边仓", ""))
        g["unit"] = g["unit"] or r.get("单位", "")
        rt = r.get("接收时间", "")
        if rt and (not g["receive_time"] or rt < g["receive_time"]):
            g["receive_time"] = rt
        it = r.get("最新发料单时间", "")
        if it and it > g["issue_time"]:
            g["issue_time"] = it
        # 保留原始条码行（含WO/物料/条码/现存量/时间）
        raw_rows.append({
            "指定工单": wo,
            "物料编号": mat,
            "物料描述": r.get("物料描述", ""),
            "条码": r.get("条码", ""),
            "现存量": qty,
            "单位": r.get("单位", ""),
            "线边仓": r.get("线边仓描述", r.get("线边仓", "")),
            "接收时间": r.get("接收时间", ""),
            "最新发料时间": r.get("最新发料单时间", ""),
        })

    return grouped, raw_rows


def load_nwms_lines():
    """加载 NWMS 发料行明细，可选（文件不存在时返回空）"""
    path = BASE / "nwms_issue_details_latest.json"
    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        rows = json.load(f)

    # 按 componentCode 索引，同时处理 _workOrderNum 可能含多个工单（逗号分隔）
    # 返回结构：{componentCode: [{instructionDocId, workOrderNums:set, demandQty, actualQty, status, ...}]}
    by_component = defaultdict(list)
    for r in rows:
        comp = (r.get("componentCode") or "").strip()
        if not comp:
            continue
        wo_raw = (r.get("_workOrderNum") or "").strip()
        wos = set(w.strip() for w in wo_raw.split(",") if w.strip())
        related = (r.get("relatedWoLine") or "").strip()
        related_wos = set(w.strip() for w in related.split(",") if w.strip())
        wos |= related_wos

        try:
            demand = float(r.get("demandQuantity") or 0)
        except (ValueError, TypeError):
            demand = 0.0
        try:
            actual = float(r.get("actualQuantity") or 0)
        except (ValueError, TypeError):
            actual = 0.0

        by_component[comp].append({
            "docId": r.get("_instructionDocId", ""),
            "docNum": r.get("_demandListNumber", ""),
            "workOrders": wos,
            "demandQty": demand,
            "actualQty": actual,
            "status": r.get("status", ""),
            "productionLine": r.get("_productionLine", ""),
            "warehouse": r.get("_wareHouse", ""),
            "docStatus": r.get("_docStatus", ""),
            "ppStartTime": r.get("_ppStartTime", ""),
        })

    print(f"  NWMS 发料行: {sum(len(v) for v in by_component.values())} 条，"
          f"涉及 {len(by_component)} 种物料")
    return by_component


# ═══════════════════════════════════════════════════════════════════════════════
# 分析 1：退料预警（离场审计）
# 条件：工单已完成 AND 该工单+物料仍有线边仓库存
# ═══════════════════════════════════════════════════════════════════════════════

def build_return_alert(orders, bom_index, inventory):
    """生成退料预警报告"""
    results = []

    for (wo, mat), inv in inventory.items():
        order = orders.get(wo)
        if not order:
            continue
        if order.get("statusDesc") not in COMPLETED_STATUSES:
            continue

        bom = bom_index.get((wo, mat))
        qty_done = float(order.get("qtyDone") or 0)
        qty_ordered = float(order.get("qtyOrdered") or 0)

        if bom:
            unit_qty = float(bom.get("qty") or 0)
            sum_qty = float(bom.get("sumQty") or 0)
            send_qty = float(bom.get("sendQty") or 0)
            theoretical_remainder = sum_qty - qty_done * unit_qty
        else:
            unit_qty = sum_qty = send_qty = theoretical_remainder = None

        actual_inv = inv["qty"]
        deviation = (actual_inv - theoretical_remainder) if theoretical_remainder is not None else None

        results.append({
            "工单号": wo,
            "物料编号": mat,
            "物料描述": inv["desc"],
            "线边仓": inv["warehouse"],
            "单位": inv["unit"],
            "实际库存(合计)": round(actual_inv, 2),
            "条码数": inv["barcodes"],
            "barcode_list": inv.get("barcode_list", []),
            "工单状态": order.get("statusDesc", ""),
            "计划数量": qty_ordered,
            "完工数量": qty_done,
            "BOM单件用量": unit_qty,
            "BOM总需求量": sum_qty,
            "已发料量(sendQty)": send_qty,
            "理论余料": round(theoretical_remainder, 2) if theoretical_remainder is not None else "",
            "偏差(实际-理论)": round(deviation, 2) if deviation is not None else "",
            "接收时间": inv["receive_time"],
            "最新发料时间": inv["issue_time"],
            "is_legacy": _is_legacy(inv["receive_time"]),
            "aging_days": round((datetime.now() - _parse_date(inv["receive_time"])).total_seconds() / 86400, 1) if _parse_date(inv["receive_time"]) else -1.0,
        })

    results.sort(key=lambda x: (
        -(x["偏差(实际-理论)"] if isinstance(x["偏差(实际-理论)"], float) else 0),
        x["工单号"],
    ))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 分析 2：超发预警（进场审计）
# 数据来源：NWMS woissueLineDetail 的 actualQuantity vs demandQuantity
# ═══════════════════════════════════════════════════════════════════════════════

def build_issue_audit(nwms_by_component, orders, bom_index):
    """生成超发预警报告（需要 NWMS 数据）"""
    results = []
    nwms_total = sum(len(v) for v in nwms_by_component.values())
    nwms_matched = 0
    seen = set()

    # 以 NWMS 发料行为主表
    for comp, lines in nwms_by_component.items():
        for ln in lines:
            doc_id = ln["docId"]
            key = (doc_id, comp)
            if key in seen:
                continue
            seen.add(key)

            # ── 分析层过滤：关联工单必须存在于 IMES 工单集合 ──
            has_matched_wo = any(wo in orders for wo in ln["workOrders"])
            if not has_matched_wo:
                continue  # 丢弃，计入未匹配统计
            nwms_matched += 1

            demand = ln["demandQty"]
            actual = ln["actualQty"]
            over_issue = actual - demand
            over_rate = (over_issue / demand * 100) if demand > 0 else 0

            # 尝试关联 IMES 工单（取第一个匹配的工单）
            matched_wo = ""
            matched_order = None
            matched_bom = None
            for wo in ln["workOrders"]:
                if wo in orders:
                    matched_wo = wo
                    matched_order = orders[wo]
                    matched_bom = bom_index.get((wo, comp))
                    break

            # BOM 标准需求量及其超发计算
            bom_sum_qty = float(matched_bom.get("sumQty") or 0) if matched_bom else 0.0
            over_vs_bom = round(actual - bom_sum_qty, 2) if bom_sum_qty > 0 else ""
            over_vs_bom_rate = round((actual - bom_sum_qty) / bom_sum_qty * 100, 1) if bom_sum_qty > 0 else ""
            if over_vs_bom == "":
                over_vs_bom_label = "(BOM无数据)"
            elif isinstance(over_vs_bom, float) and over_vs_bom > 0.01:
                over_vs_bom_label = "⚠️ 超发(BOM)"
            elif isinstance(over_vs_bom, float) and over_vs_bom >= -0.01:
                over_vs_bom_label = "✅ 正常(BOM)"
            else:
                over_vs_bom_label = "🔽 少发(BOM)"

            results.append({
                "备料单ID": doc_id,
                "备料单号": ln["docNum"],
                "备料单状态": ln["docStatus"],
                "关联工单": ",".join(sorted(ln["workOrders"])),
                "物料编号": comp,
                # NWMS 口径
                "计划发料量(demandQty)": round(demand, 2),
                "实际发料量(actualQty)": round(actual, 2),
                "超发量": round(over_issue, 2),
                "超发率(%)": round(over_rate, 1),
                "是否超发": "⚠️ 超发" if over_issue > 0.01 else ("✅ 正常" if over_issue >= -0.01 else "🔽 少发"),
                # BOM 口径
                "BOM标准需求量(sumQty)": bom_sum_qty if bom_sum_qty > 0 else "",
                "超发量(vs BOM)": over_vs_bom,
                "超发率%(vs BOM)": over_vs_bom_rate,
                "是否超发(BOM口径)": over_vs_bom_label,
                # 其他信息
                "发料状态": ln["status"],
                "产线": ln["productionLine"],
                "仓库": ln["warehouse"],
                "IMES工单状态": matched_order.get("statusDesc", "") if matched_order else "",
                "计划发料日期": ln.get("ppStartTime", ""),
            })

    # 按超发量降序排列（最严重的排前面）
    results.sort(key=lambda x: -(x["超发量"] if isinstance(x["超发量"], float) else 0))
    return results, nwms_total, nwms_matched


# ═══════════════════════════════════════════════════════════════════════════════
# 保存
# ═══════════════════════════════════════════════════════════════════════════════

def save_csv(rows, filename):
    if not rows:
        print(f"  [SKIP] {filename} — 无数据")
        return
    path = BASE / filename
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [SAVE] {path}  ({len(rows)} 行)")


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

def _parse_date(date_str: str):
    """尝试从字符串解析日期，失败返回 None
    兼容格式：
      '2026-02-18 14:54:53'  (连字符，标准)
      '2026/2/18 14:54:53'   (斜杠，SSRS 库存 CSV 实际格式)
      '2026/2/6 9:57:22'     (斜杠 + 单位数月/日/时)
    """
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        # 先取空格前的日期部分（避免 [:10] 截入时间）
        date_part = s.split(" ")[0].replace("/", "-")
        # 补齐单位数月/日：2026-2-6 → 2026-02-06
        parts = date_part.split("-")
        if len(parts) == 3:
            date_part = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        return datetime.strptime(date_part, "%Y-%m-%d")
    except (ValueError, TypeError, IndexError):
        return None

def _is_legacy(receive_time_str: str) -> bool:
    d = _parse_date(receive_time_str)
    return d is None or d < datetime(2026, 1, 1)





# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def run():
    print("=" * 60)
    print("物料流转双向审计报告生成器")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 加载数据
    print("\n[1/4] 加载 IMES 工单数据...")
    orders = load_shop_orders()
    print(f"  工单: {len(orders)} 条")

    print("[2/4] 加载 IMES BOM 数据...")
    bom_index = load_bom()
    print(f"  BOM行: {len(bom_index)} 条")

    print("[3/4] 加载 SSRS 线边仓库存...")
    inventory, inventory_raw = load_inventory()
    print(f"  有效库存组合(工单+物料): {len(inventory)} 组，条码行: {len(inventory_raw)} 条")

    print("[4/4] 加载 NWMS 发料行明细（可选）...")
    nwms_lines = load_nwms_lines()
    if nwms_lines is None:
        print("  [跳过] nwms_issue_details_latest.json 不存在，跳过进场审计")
        print("  运行 'python3 src/scrapers/nwms_scraper.py' 获取 NWMS 数据")

    # 分析 1：退料预警
    print("\n─── 退料预警（离场审计）────────────────────────────")
    alert = build_return_alert(orders, bom_index, inventory)

    print(f"  完工工单仍有库存的组合: {len(alert)} 组")
    over_positive = [r for r in alert if isinstance(r["偏差(实际-理论)"], float) and r["偏差(实际-理论)"] > 0.01]
    print(f"  其中偏差 > 0（账面超发/多余）: {len(over_positive)} 组")
    save_csv(alert, "alert_report.csv")

    # 退料预警明细（条码级，供 Page 2 操作明细使用）
    alert_wo_mat = {(r["工单号"], r["物料编号"]): r for r in alert}
    detail_rows = []
    for row in inventory_raw:
        key = (row["指定工单"], row["物料编号"])
        if key not in alert_wo_mat:
            continue
        a = alert_wo_mat[key]
        detail_rows.append({
            **row,
            "工单状态": a.get("工单状态", ""),
            "完工数量": a.get("完工数量", ""),
            "偏差(所属组)": a.get("偏差(实际-理论)", ""),
            "理论余料": a.get("理论余料", ""),
        })
    detail_rows.sort(key=lambda x: (x["指定工单"], x["物料编号"]))
    save_csv(detail_rows, "alert_report_detail.csv")
    print(f"  条码明细行数: {len(detail_rows)}")

    # 分析 2：超发预警（NWMS 数据可用时）
    if nwms_lines:
        print("\n─── 超发预警（进场审计）────────────────────────────")
        issue_audit, nwms_total, nwms_matched = build_issue_audit(nwms_lines, orders, bom_index)
        over_issued = [r for r in issue_audit if r["超发量"] > 0.01]
        print(f"  发料行总计: {len(issue_audit)} 条")
        print(f"  其中超发: {len(over_issued)} 条")
        if issue_audit:
            top5 = over_issued[:5]
            for r in top5:
                print(f"  ⚠️  {r['物料编号']} | 计划={r['计划发料量(demandQty)']} 实发={r['实际发料量(actualQty)']} "
                      f"超发={r['超发量']} | 备料单={r['备料单号']}")
        save_csv(issue_audit, "issue_audit_report.csv")
    else:
        issue_audit = []

    # 汇总
    print("\n─── 汇总 ───────────────────────────────────────────")
    print(f"  退料预警组数: {len(alert)}")
    print(f"  偏差>0 (需立即处理): {len(over_positive)}")
    if nwms_lines:
        print(f"  超发发料行: {len(over_issued)}")
    print("\n[完成] 报告已保存到 data/raw/")
    
    # ── 库龄与分类统计 (Phase 3) ──
    NOW = datetime.now()
    def _aging_days(receive_time_str: str) -> float:
        d = _parse_date(receive_time_str)
        if d is None:
            return -1.0
        return (NOW - d).total_seconds() / 86400

    confirmed_alerts = [
        r for r in alert
        if not r.get("is_legacy")
        and r.get("工单号") in orders
    ]
    confirmed_alerts_excl = [
        r for r in confirmed_alerts
        if r.get("物料编号", "") not in COMMON_MATERIALS
    ]
    unmatched_current = [
        (wo, mat) for (wo, mat), inv in inventory.items()
        if not _is_legacy(inv["receive_time"])
        and wo not in orders
    ]
    legacy_items = [
        (wo, mat) for (wo, mat), inv in inventory.items()
        if _is_legacy(inv["receive_time"])
    ]

    aging_dist = {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}
    aging_hours_list = []
    aging_hours_list_excl = []

    for r in confirmed_alerts:
        days = _aging_days(r.get("接收时间", ""))
        if days < 0:
            continue
        
        hours = days * 24
        aging_hours_list.append(hours)
        if r.get("物料编号", "") not in COMMON_MATERIALS:
            aging_hours_list_excl.append(hours)
        if days <= 1:
            aging_dist["le1"] += 1
        elif days <= 3:
            aging_dist["d1_3"] += 1
        elif days <= 7:
            aging_dist["d3_7"] += 1
        elif days <= 14:
            aging_dist["d7_14"] += 1
        elif days <= 30:
            aging_dist["d14_30"] += 1
        else:
            aging_dist["gt30"] += 1

    avg_aging_current = round(sum(aging_hours_list) / len(aging_hours_list), 1) if aging_hours_list else 0.0
    avg_aging_current_excl = round(sum(aging_hours_list_excl) / len(aging_hours_list_excl), 1) if aging_hours_list_excl else 0.0

    # ── 数据质量统计 ──
    legacy_rows = [r for r in inventory_raw if _is_legacy(r.get("接收时间", ""))]
    alert_current = [r for r in alert if not r.get("is_legacy")]
    alert_matched = len(alert_current)
    alert_unmatched = len([
        (wo, mat) for (wo, mat), inv in inventory.items()
        if not _is_legacy(inv["receive_time"])
        and (wo, mat) not in {(r["工单号"], r["物料编号"]) for r in alert_current}
        and wo not in orders  # 有库存但工单不存在
    ])
    alert_match_rate = round(
        alert_matched / (alert_matched + alert_unmatched) * 100, 1
    ) if (alert_matched + alert_unmatched) > 0 else 0.0

    quality_stats = {
        "inventory_total": len(inventory_raw),
        "inventory_legacy": len(legacy_rows),
        "inventory_current": len(inventory_raw) - len(legacy_rows),
        "orders_total": len(orders),
        "alert_matched": alert_matched,
        "alert_unmatched": alert_unmatched,
        "alert_match_rate": alert_match_rate,
        "nwms_lines_total": nwms_total if nwms_lines else 0,
        "nwms_lines_matched": nwms_matched if nwms_lines else 0,
        "nwms_match_rate": round(nwms_matched / nwms_total * 100, 1) if nwms_lines and nwms_total > 0 else 0.0,
        "confirmed_alert_count": len(confirmed_alerts),
        "confirmed_alert_count_excl": len(confirmed_alerts_excl),
        "unmatched_current_count": len(unmatched_current),
        "legacy_count": len(legacy_items),
        "avg_aging_hours_current": avg_aging_current,
        "avg_aging_hours_excl": avg_aging_current_excl,
        "aging_distribution": aging_dist,
    }
    
    return alert, issue_audit, quality_stats

if __name__ == "__main__":
    run()

