"""
NWMS 发料明细爬虫 - 内网 NWMS 仓储系统
接口：
  - 备料单头表：GET .../mt-work-orders/ins_woissue_head
  - 发料明细：  GET .../mt-work-orders/woissueLineActualDetail?instructionId=xxx

依赖工单爬虫：需先运行 shop_order_scraper.py 获取工单列表。
              或直接全量拉取所有备料单的明细。

使用前：
  1. 浏览器打开 http://10.80.35.11:91，登录
  2. F12 → Network → 复制 Authorization 头中 bearer 后面的 Token
  3. 粘贴到下方 NWMS_CONFIG["token"]

运行：
  cd /home/chenweijie/projects/matetial_monitor

  # 模式1: 拉取全部备料单的发料明细（默认）
  python3 src/scrapers/nwms_scraper.py

  # 模式2: 只拉取指定工单号相关的发料明细
  python3 src/scrapers/nwms_scraper.py --work-order 262200120710

  # 模式3: 只拉取 COMPLETED 状态的备料单
  python3 src/scrapers/nwms_scraper.py --status COMPLETED
"""

import requests
import json
import csv
import time
from datetime import datetime
from pathlib import Path

# ─── 配置区（NWMS Token 过期后只需更新这里）───────────────────────────────────
NWMS_CONFIG = {
    "base_url": "http://10.80.35.11:8080/nwms/v1/9",
    "token": "e5d87dcf-83fa-4bec-aa3d-c8d3d5b56c7b",  # ← 过期后替换
    "site_id": "2.1",
    "frontend_url": "http://10.80.35.11:91",
    "page_size": 200,  # 每页条数
}

NWMS_HEADERS = {
    "accept": "*/*",
    "authorization": f"bearer {NWMS_CONFIG['token']}",
    "origin": NWMS_CONFIG["frontend_url"],
    "referer": f"{NWMS_CONFIG['frontend_url']}/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


# ═══════════════════════════════════════════════════════════════════════════════
# 备料单头表拉取
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_issue_head_page(page: int, **extra_params) -> dict:
    """拉取备料单头表单页"""
    url = f"{NWMS_CONFIG['base_url']}/mt-work-orders/ins_woissue_head"
    params = {
        "page": page,
        "size": NWMS_CONFIG["page_size"],
        "siteId": NWMS_CONFIG["site_id"],
        **extra_params,
    }
    resp = requests.get(url, headers=NWMS_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_issue_heads(status: str = None, work_order: str = None, start_date: str = "2026-01-01") -> list[dict]:
    """
    分页拉取全部备料单头表
    status: 可选，筛选状态（如 COMPLETED / RELEASED）
    work_order: 可选，按工单号筛选
    start_date: 筛选 ppStartTime >= 该日期的备料单
    """
    all_heads = []
    page = 0
    extra = {}
    if status:
        extra["instructionDocStatus"] = status
    if work_order:
        extra["workOrderNum"] = work_order

    filter_desc = f"状态={status}" if status else "全部"
    if work_order:
        filter_desc += f" | 工单={work_order}"
    print(f"[INFO] 开始拉取备料单头表 | 筛选: {filter_desc}")

    while True:
        try:
            data = fetch_issue_head_page(page, **extra)
        except requests.RequestException as e:
            print(f"[ERROR] 第 {page} 页请求失败: {e}")
            break

        rows = data.get("data", data).get("rows", data.get("rows", {}))
        if isinstance(rows, dict):
            content = rows.get("content", [])
            total = rows.get("totalElements", 0)
        elif isinstance(rows, list):
            content = rows
            total = len(rows)
        else:
            content = []
            total = 0

        if not content:
            if page == 0:
                print(f"[WARN] 第 0 页无数据，请检查 Token 或筛选条件")
            break

        # 按 start_date 过滤
        valid_content = []
        for row in content:
            pp_start = row.get("ppStartTime", "") or ""
            if pp_start and pp_start[:10] < start_date:
                continue
            valid_content.append(row)

        all_heads.extend(valid_content)
        if page == 0:
            print(f"  总记录数: {total}")
        print(f"  → 第 {page + 1} 页: 获取 {len(valid_content)} 条(原始 {len(content)} 条)，累计 {len(all_heads)}")

        # 整页数据均早于 start_date，后续页只会更旧，提前退出
        if len(valid_content) == 0 and len(all_heads) > 0:
            print(f"  [早退] 整页数据均早于 {start_date}，停止翻页")
            break

        if len(all_heads) >= total:
            break
        if len(content) < NWMS_CONFIG["page_size"]:
            break

        page += 1
        time.sleep(0.3)

    print(f"[INFO] 备料单拉取完成，共 {len(all_heads)} 条")
    return all_heads


# ═══════════════════════════════════════════════════════════════════════════════
# 发料行项目拉取（步骤1：woissueLineDetail/{instructionDocId}/）
# 返回字段：instructionId（行级ID）、componentCode、demandQuantity、actualQuantity 等
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_issue_lines_for_doc(instruction_doc_id: str) -> list[dict]:
    """拉取单个备料单的全部发料行项目（自动翻页）"""
    url = f"{NWMS_CONFIG['base_url']}/mt-work-orders/woissueLineDetail/{instruction_doc_id}/"
    all_lines = []
    page = 0

    while True:
        params = {"page": page, "size": NWMS_CONFIG["page_size"]}
        try:
            resp = requests.get(url, headers=NWMS_HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"    [ERROR] woissueLineDetail/{instruction_doc_id}/ 第{page}页: {e}")
            break

        rows = data.get("data", data).get("rows", data.get("rows", {}))
        if isinstance(rows, dict):
            content = rows.get("content", [])
            total = rows.get("totalElements", 0)
        elif isinstance(rows, list):
            content = rows
            total = len(rows)
        else:
            content = []
            total = 0

        if not content:
            break

        all_lines.extend(content)

        if len(all_lines) >= total:
            break
        if len(content) < NWMS_CONFIG["page_size"]:
            break

        page += 1
        time.sleep(0.15)

    return all_lines


# ═══════════════════════════════════════════════════════════════════════════════
# 扫码实发记录拉取（步骤2：woissueLineActualDetail?instructionId={行级ID}）
# 返回字段：barcode、executeQuantity、executeTime、fromWarehouse、toWarehouse 等
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_scan_records_for_line(instruction_id: str) -> list[dict]:
    """拉取单条发料行的全部扫码实发记录（自动翻页）"""
    url = f"{NWMS_CONFIG['base_url']}/mt-work-orders/woissueLineActualDetail"
    all_records = []
    page = 0

    while True:
        params = {"instructionId": instruction_id, "page": page, "size": NWMS_CONFIG["page_size"]}
        try:
            resp = requests.get(url, headers=NWMS_HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"    [ERROR] woissueLineActualDetail/{instruction_id} 第{page}页: {e}")
            break

        rows = data.get("data", data).get("rows", data.get("rows", {}))
        if isinstance(rows, dict):
            content = rows.get("content", [])
            total = rows.get("totalElements", 0)
        elif isinstance(rows, list):
            content = rows
            total = len(rows)
        else:
            content = []
            total = 0

        if not content:
            break

        all_records.extend(content)

        if len(all_records) >= total:
            break
        if len(content) < NWMS_CONFIG["page_size"]:
            break

        page += 1
        time.sleep(0.15)

    return all_records


def fetch_all_issue_details(heads: list[dict], fetch_scans: bool = False) -> list[dict]:
    """
    批量拉取所有备料单的发料行明细（两步法）
      步骤1: woissueLineDetail/{instructionDocId}/ → 行级 demandQuantity/actualQuantity
      步骤2(可选): woissueLineActualDetail?instructionId={line.instructionId} → 扫码记录汇总
    每条行明细附加头表关键字段（工单号、产线等）
    """
    all_details = []
    total = len(heads)
    empty_count = 0
    error_count = 0

    print(f"[INFO] 开始拉取发料行明细，共 {total} 个备料单" + (" + 扫码记录汇总" if fetch_scans else ""))

    for i, head in enumerate(heads, 1):
        doc_id = str(head.get("instructionDocId", ""))
        doc_num = head.get("demandListNumber", "")
        wo_num = head.get("workOrderNum", "")
        line = head.get("productionLine", "")
        warehouse = head.get("wareHouse", "")
        doc_status = head.get("instructionDocStatus", "")
        pp_start_time = head.get("ppStartTime", "")

        if not doc_id:
            continue

        try:
            lines = fetch_issue_lines_for_doc(doc_id)
        except Exception as e:
            error_count += 1
            if i % 50 == 0 or i == total:
                print(f"  [{i}/{total}] (ERROR) {doc_num}: {e}")
            continue

        if not lines:
            empty_count += 1
        else:
            for ln in lines:
                ln["_instructionDocId"] = doc_id
                ln["_demandListNumber"] = doc_num
                ln["_workOrderNum"] = wo_num
                ln["_productionLine"] = line
                ln["_wareHouse"] = warehouse
                ln["_docStatus"] = doc_status
                ln["_ppStartTime"] = pp_start_time

                # 可选：拉取扫码实发记录，汇总 scanCount / scanExecuteQty
                if fetch_scans:
                    line_id = str(ln.get("instructionId", ""))
                    if line_id:
                        scans = fetch_scan_records_for_line(line_id)
                        ln["_scanCount"] = len(scans)
                        ln["_scanExecuteQty"] = sum(
                            float(s.get("executeQuantity") or 0) for s in scans
                        )
                        time.sleep(0.1)

            all_details.extend(lines)

        if i % 20 == 0 or i == total:
            print(f"  [{i}/{total}] 累计 {len(all_details)} 条行明细"
                  f" | 空={empty_count} | 错误={error_count}"
                  f" | 当前: {doc_num} → {len(lines) if lines else 0} 条")

        time.sleep(0.2)

    print(f"[INFO] 发料行明细拉取完成")
    print(f"  总计: {len(all_details)} 条行明细")
    print(f"  空备料单: {empty_count} 个")
    print(f"  请求错误: {error_count} 个")

    return all_details


# ═══════════════════════════════════════════════════════════════════════════════
# 保存
# ═══════════════════════════════════════════════════════════════════════════════

def save_json(data: list[dict], filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] JSON → {path}")
    return path


def save_csv(data: list[dict], filename: str) -> Path:
    if not data:
        print("[WARN] 无数据可保存")
        return None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    keys = list(data[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"[SAVE] CSV  → {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def run(status: str = None, work_order: str = None, fetch_scans: bool = False, start_date: str = "2026-01-01"):
    """主入口"""
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # 1. 拉取备料单头表
    heads = fetch_all_issue_heads(status=status, work_order=work_order, start_date=start_date)
    if not heads:
        print("[ERROR] 未获取到备料单数据，请检查 Token 或网络")
        return

    # 保存头表
    save_json(heads, f"nwms_issue_heads_{ts}.json")
    save_csv(heads, f"nwms_issue_heads_{ts}.csv")
    save_json(heads, "nwms_issue_heads_latest.json")
    save_csv(heads, "nwms_issue_heads_latest.csv")

    # 2. 拉取发料行明细（步骤1: woissueLineDetail + 可选步骤2: woissueLineActualDetail）
    details = fetch_all_issue_details(heads, fetch_scans=fetch_scans)
    if details:
        save_json(details, f"nwms_issue_details_{ts}.json")
        save_csv(details, f"nwms_issue_details_{ts}.csv")
        save_json(details, "nwms_issue_details_latest.json")
        save_csv(details, "nwms_issue_details_latest.csv")

        # 打印字段结构（首次运行时很有用）
        print(f"\n[INFO] 发料明细字段列表:")
        for key in details[0].keys():
            sample_val = details[0].get(key)
            print(f"  • {key}: {repr(sample_val)[:80]}")
    else:
        print("[WARN] 未获取到任何发料明细")

    # 3. 健康检查
    print(f"\n[健康检查]")
    print(f"  备料单: {len(heads)} 条")
    print(f"  发料明细: {len(details)} 条")

    # 统计有明细的备料单数
    docs_with_detail = set()
    for d in details:
        docs_with_detail.add(d.get("_instructionDocId", ""))
    print(f"  有明细的备料单: {len(docs_with_detail)} / {len(heads)} 个")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NWMS 发料明细爬虫")
    parser.add_argument("--status", default=None,
                        help="筛选备料单状态: COMPLETED / RELEASED / CANCEL")
    parser.add_argument("--work-order", default=None,
                        help="按工单号筛选备料单")
    parser.add_argument("--scan-records", action="store_true",
                        help="同时拉取每行的扫码实发记录（慢，数据量大）")
    parser.add_argument("--test", action="store_true",
                        help="测试模式：只拉取前5个备料单的明细")
    parser.add_argument("--start", default="2026-01-01",
                        help="只拉取 ppStartTime >= 此日期的备料单（默认 2026-01-01）")
    args = parser.parse_args()

    if args.test:
        print(f"[TEST] 测试模式：只拉取前5个备料单 (start >= {args.start})")
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        heads = fetch_all_issue_heads(status=args.status, work_order=args.work_order, start_date=args.start)
        if heads:
            test_heads = heads[:5]
            print(f"[TEST] 取前 {len(test_heads)} 个备料单测试...")
            details = fetch_all_issue_details(test_heads, fetch_scans=args.scan_records)
            if details:
                save_json(details, "nwms_issue_details_test.json")
                print(f"\n[TEST] 发料行明细字段列表:")
                for key in details[0].keys():
                    sample_val = details[0].get(key)
                    print(f"  • {key}: {repr(sample_val)[:80]}")
            else:
                print("[TEST] 前5个备料单均无行明细")
    else:
        run(status=args.status, work_order=args.work_order, fetch_scans=args.scan_records, start_date=args.start)
