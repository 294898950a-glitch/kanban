"""
工单数据爬虫 - IMES 内网系统
接口：http://10.80.35.11:8080/imes-service/v1/0/shopOrder
"""

import os
import requests
import json
import csv
import time
from datetime import datetime
from pathlib import Path

# ─── 配置区（优先读环境变量，回退到硬编码值）────────────────────────────────
CONFIG = {
    "base_url": "http://10.80.35.11:8080/imes-service/v1/0/shopOrder",
    "token": os.environ.get("IMES_TOKEN", "4b0e382c-de14-4e90-b4f4-e886ddb2b215"),
    "site": "2010",
    "page_size": 100,  # 每页条数，可调大以减少请求次数
}

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "authorization": f"Bearer {CONFIG['token']}",
    "menu": "",
    "system": "IMES",
    "origin": "http://10.80.35.11:30088",
    "referer": "http://10.80.35.11:30088/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


def fetch_page(page: int, start_date: str, classes: str = "A") -> dict:
    """拉取单页工单数据"""
    params = {
        "signTime": int(time.time() * 1000),
        "page": page,
        "size": CONFIG["page_size"],
        "classes": classes,
        "plannedCheck": "false",
        "plannedStartDate": start_date,
        "showMaoPao": "false",
        "site": CONFIG["site"],
        "language": "zh_CN",
    }
    resp = requests.get(CONFIG["base_url"], headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_orders(start_date: str, classes: str = "A") -> list[dict]:
    """
    分页拉取全部工单
    start_date 格式: "2026-01-01 00:00:00"（不传结束日期，避免漏掉计划完工在未来的在制工单）
    """
    all_orders = []
    page = 0

    print(f"[INFO] 开始拉取工单 | 计划开始日期 ≥ {start_date[:10]} | 类型: {classes}")

    while True:
        try:
            data = fetch_page(page, start_date, classes)
        except requests.RequestException as e:
            print(f"[ERROR] 第 {page} 页请求失败: {e}")
            break

        # ── 响应结构: {"success":true, "rows": {"content":[...], "totalElements":N}} ──
        rows = data.get("rows", {})
        content = rows.get("content", [])

        if not content:
            print(f"[WARN] 第 {page} 页无数据，停止翻页")
            break

        all_orders.extend(content)
        total = rows.get("totalElements", 0)
        print(f"  → 第 {page + 1} 页: 获取 {len(content)} 条，累计 {len(all_orders)} / {total} 条")

        if len(all_orders) >= total:
            break
        if len(content) < CONFIG["page_size"]:
            break  # 不足一页，说明已是最后一页

        page += 1
        time.sleep(0.3)  # 礼貌性延迟，避免压垮内网服务

    print(f"[INFO] 拉取完成，共 {len(all_orders)} 条工单")
    return all_orders


def save_json(orders: list[dict], filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] JSON → {path}")
    return path


def save_csv(orders: list[dict], filename: str) -> Path:
    if not orders:
        print("[WARN] 无数据可保存")
        return None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    keys = list(orders[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(orders)
    print(f"[SAVE] CSV  → {path}")
    return path


def run(start_date: str = None):
    """主入口"""
    today = datetime.now().strftime("%Y-%m-%d")
    start_date = start_date or f"{today} 00:00:00"

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    orders = fetch_all_orders(start_date, classes="A")

    if orders:
        save_json(orders, f"shop_orders_{ts}.json")
        save_csv(orders, f"shop_orders_{ts}.csv")
        save_json(orders, "shop_orders_latest.json")
        save_csv(orders, "shop_orders_latest.csv")
    else:
        print("[WARN] 未获取到任何工单数据，请检查 token 是否过期或日期范围是否正确")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IMES 工单数据爬虫")
    parser.add_argument("--start", default=None, help="计划开始日期，格式: 2026-01-01 00:00:00")
    args = parser.parse_args()

    run(args.start)
