"""
BOM 数据爬虫 - 按工单逐个拉取标准 BOM
接口：http://10.80.35.11:8080/imes-service/v1/0/shopOrder/bom
"""

import requests
import json
import csv
import time
from pathlib import Path
from src.scrapers.shop_order_scraper import CONFIG, HEADERS  # 复用配置

BOM_URL = "http://10.80.35.11:8080/imes-service/v1/0/shopOrder/bom"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


def fetch_bom(shop_order: str) -> list[dict]:
    """拉取单个工单的 BOM 明细"""
    params = {
        "signTime": int(time.time() * 1000),
        "shopOrder": shop_order,
        "site": CONFIG["site"],
    }
    resp = requests.get(BOM_URL, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("rows", [])


def fetch_all_boms(shop_orders: list[str]) -> list[dict]:
    """
    批量拉取所有工单的 BOM，返回扁平化明细表
    每行 = 一个工单下的一条 BOM 物料
    """
    all_rows = []
    total = len(shop_orders)

    for i, so in enumerate(shop_orders, 1):
        try:
            rows = fetch_bom(so)
            all_rows.extend(rows)
            if i % 10 == 0 or i == total:
                print(f"  [{i}/{total}] {so}: {len(rows)} 条BOM行，累计 {len(all_rows)} 条")
        except requests.RequestException as e:
            print(f"  [ERROR] {so} 请求失败: {e}")
        time.sleep(0.2)  # 礼貌性延迟

    print(f"[INFO] BOM 拉取完成，共 {len(all_rows)} 条明细")
    return all_rows


def load_shop_orders_from_file(path: Path = None) -> list[str]:
    """从已拉取的工单 JSON 文件中读取工单号列表"""
    path = path or (OUTPUT_DIR / "shop_orders_latest.json")
    with open(path, encoding="utf-8") as f:
        orders = json.load(f)
    return [o["shopOrder"] for o in orders]


def save_bom(rows: list[dict], filename: str):
    if not rows:
        print("[WARN] 无 BOM 数据")
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = OUTPUT_DIR / filename.replace(".csv", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] JSON → {json_path}")

    # CSV
    csv_path = OUTPUT_DIR / filename
    keys = list(rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[SAVE] CSV  → {csv_path}")


def run(shop_order_file: Path = None):
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    print("[INFO] 读取工单列表...")
    shop_orders = load_shop_orders_from_file(shop_order_file)
    print(f"[INFO] 共 {len(shop_orders)} 个工单，开始拉取 BOM...")

    rows = fetch_all_boms(shop_orders)
    save_bom(rows, f"bom_details_{ts}.csv")
    save_bom(rows, "bom_details_latest.csv")  # 固定文件名供后续引用


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IMES BOM 数据爬虫")
    parser.add_argument("--orders", default=None, help="工单JSON文件路径（默认用最新的）")
    args = parser.parse_args()
    run(Path(args.orders) if args.orders else None)
