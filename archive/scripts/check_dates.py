import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.build_report import _parse_date, _is_legacy
import csv
from pathlib import Path
from datetime import datetime

BASE = Path("data/raw")
path = BASE / "inventory_latest.csv"

with open(path, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

# 统计接收时间分布（使用修复后的 _parse_date）
before_2026 = []
since_2026 = []
empty = []

CUTOFF = datetime(2026, 1, 1)

for r in rows:
    rt = r.get("接收时间", "").strip()
    if not rt:
        empty.append(rt)
        continue
    d = _parse_date(rt)
    if d is None:
        empty.append(rt)  # 解析失败等同于空
    elif d < CUTOFF:
        before_2026.append(rt)
    else:
        since_2026.append(rt)

print(f"总行数: {len(rows)}")
print(f"接收时间为空/解析失败: {len(empty)}")
print(f"早于 2026-01-01（历史遗留）: {len(before_2026)}")
print(f"2026-01-01 及之后（当期）: {len(since_2026)}")

if before_2026:
    print(f"\n历史遗留样本（前5条）: {before_2026[:5]}")
if empty:
    print(f"\n空值/失败样本（前3条）: {[x for x in empty if x][:3]}")
