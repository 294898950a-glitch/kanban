# 第三阶段实现计划：数据治理

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 解决三系统时间窗口不对齐导致的系统性误报，建立数据质量度量基线。

**Architecture:** 在现有分析层新增「历史遗留」分层标记、NWMS 双层过滤、数据质量快照表，不改动爬虫核心逻辑，不新增前端页面。

**Tech Stack:** Python + SQLAlchemy + SQLite，改动范围：`models.py` / `build_report.py` / `sync.py` / `scheduler.py` / `nwms_scraper.py`

---

## Task 1: 新增 `DataQualitySnapshot` 模型 + `AlertReportSnapshot.is_legacy` 字段

**Files:**
- Modify: `src/db/models.py`

**Step 1: 在 `AlertReportSnapshot` 末尾新增 `is_legacy` 字段**

在 `last_issue_time` 字段之后、`__table_args__` 之前插入：

```python
    is_legacy = Column(Integer, default=0)  # 1=历史遗留(接收时间<2026或为空)，0=当期
```

**Step 2: 在文件末尾新增 `DataQualitySnapshot` 类**

```python
class DataQualitySnapshot(Base):
    __tablename__ = "data_quality_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # 线边仓分层
    inventory_total = Column(Integer, default=0)    # 总条目数
    inventory_legacy = Column(Integer, default=0)   # 历史遗留数（接收时间<2026或为空）
    inventory_current = Column(Integer, default=0)  # 当期数（接收时间>=2026）

    # IMES 工单关联率
    orders_total = Column(Integer, default=0)       # IMES 工单总数
    alert_matched = Column(Integer, default=0)      # 当期库存匹配到工单的组合数
    alert_unmatched = Column(Integer, default=0)    # 当期库存未匹配到工单的组合数
    alert_match_rate = Column(Float, default=0.0)   # 匹配率(%)

    # NWMS 关联率
    nwms_lines_total = Column(Integer, default=0)   # NWMS 发料行总数
    nwms_lines_matched = Column(Integer, default=0) # 关联工单在 IMES 中存在的行数
    nwms_match_rate = Column(Float, default=0.0)    # 匹配率(%)
```

**Step 3: 在 `main.py` 的 import 中引入新模型**

在 `src/api/main.py` 的 import 行更新：
```python
from src.db.models import KPIHistory, AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot
```

**Step 4: 验证建表**

```bash
python3 -c "
from src.db.database import engine, Base
from src.db import models
Base.metadata.create_all(bind=engine)
print('OK')
"
```

Expected: 输出 `OK`，无报错。SQLite 中新建 `data_quality_snapshots` 表，`alert_report_snapshots` 新增 `is_legacy` 列。

**Step 5: Commit**

```bash
git add src/db/models.py src/api/main.py
git commit -m "feat(db): add DataQualitySnapshot table and is_legacy field to AlertReportSnapshot"
```

---

## Task 2: `build_report.py` — 退料预警新增历史遗留分层

**Files:**
- Modify: `src/analysis/build_report.py`

**Step 1: 在 `build_return_alert()` 函数中，为每条结果打 `is_legacy` 标记**

找到 `results.append({...})` 块，在其中新增字段（约第 188-206 行）：

```python
# 判断是否历史遗留：接收时间为空，或早于 2026-01-01
receive_time_str = inv["receive_time"]
try:
    is_legacy = (
        not receive_time_str
        or datetime.strptime(receive_time_str[:10], "%Y-%m-%d") < datetime(2026, 1, 1)
    )
except (ValueError, TypeError):
    is_legacy = True

results.append({
    ...（原有字段保持不变）...
    "is_legacy": is_legacy,
})
```

**Step 2: 在 `run()` 函数中收集数据质量统计**

在 `alert = build_return_alert(...)` 之后，插入统计代码：

```python
# 数据质量统计
legacy_rows = [r for r in inventory_raw if not r.get("接收时间") or
    _parse_date(r["接收时间"]) < datetime(2026, 1, 1)]
current_rows = [r for r in inventory_raw if r not in legacy_rows]

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
```

新增辅助函数（文件顶部，紧接现有 `safe_float`/`safe_str` 之后）：

```python
def _parse_date(date_str: str):
    """尝试从字符串解析日期，失败返回 None"""
    try:
        return datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

def _is_legacy(receive_time_str: str) -> bool:
    d = _parse_date(receive_time_str)
    return d is None or d < datetime(2026, 1, 1)
```

**Step 3: 在 `run()` 中构造并返回 `quality_stats`**

修改 `run()` 末尾的 return：

```python
quality_stats = {
    "inventory_total": len(inventory_raw),
    "inventory_legacy": sum(1 for r in inventory_raw if _is_legacy(r.get("接收时间", ""))),
    "inventory_current": sum(1 for r in inventory_raw if not _is_legacy(r.get("接收时间", ""))),
    "orders_total": len(orders),
    "alert_matched": alert_matched,
    "alert_unmatched": alert_unmatched,
    "alert_match_rate": alert_match_rate,
    "nwms_lines_total": 0,   # 由进场审计部分填充
    "nwms_lines_matched": 0,
    "nwms_match_rate": 0.0,
}

return alert, issue_audit, quality_stats
```

**Step 4: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat(analysis): add is_legacy classification and quality_stats to build_report"
```

---

## Task 3: `build_report.py` — 进场审计 NWMS 双层过滤

**Files:**
- Modify: `src/analysis/build_report.py`

**Step 1: 在 `build_issue_audit()` 中过滤未关联工单的 NWMS 行**

找到 `build_issue_audit()` 函数（约第 220 行），在循环开始前统计总行数，循环中跳过无匹配工单的行：

```python
def build_issue_audit(nwms_by_component, orders, bom_index):
    results = []
    nwms_total = sum(len(v) for v in nwms_by_component.values())
    nwms_matched = 0
    seen = set()

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

            # ... 原有计算逻辑保持不变 ...
```

**Step 2: 将 NWMS 统计注入 `quality_stats`**

在 `run()` 函数的进场审计完成后，更新 quality_stats：

```python
if nwms_lines:
    issue_audit, nwms_total, nwms_matched = build_issue_audit(nwms_lines, orders, bom_index)
    quality_stats["nwms_lines_total"] = nwms_total
    quality_stats["nwms_lines_matched"] = nwms_matched
    quality_stats["nwms_match_rate"] = round(
        nwms_matched / nwms_total * 100, 1
    ) if nwms_total > 0 else 0.0
```

同步修改 `build_issue_audit()` 返回值为 `return results, nwms_total, nwms_matched`。

**Step 3: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat(analysis): add NWMS analysis-layer filter and match rate tracking"
```

---

## Task 4: `sync.py` — 适配新返回值，写入 DataQualitySnapshot

**Files:**
- Modify: `src/db/sync.py`

**Step 1: 更新 `run_and_sync()` 接收 `quality_stats`**

```python
def run_and_sync():
    print("[SYNC] 执行原分析逻辑并获取数据...")
    alert_rows, issue_rows, quality_stats = build_report_run()  # 解包三元组
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    db = SessionLocal()
    try:
        save_to_db(alert_rows, issue_rows, quality_stats, db, batch_id)
    finally:
        db.close()
```

**Step 2: 更新 `save_to_db()` 签名，写入 DataQualitySnapshot**

```python
def save_to_db(alert_rows, issue_rows, quality_stats, session, batch_id):
    # ... 原有 KPI / Alert / Issue 写入逻辑不变 ...

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
    print(f"  [DB] 数据质量快照写入完成")
```

**Step 3: 更新 `KPIHistory` 写入逻辑**

`high_risk_count` 只统计非历史遗留的高风险组：

```python
high_risk_count=len([
    r for r in alert_rows
    if safe_float(r.get("偏差(实际-理论)")) > 0.01
    and not r.get("is_legacy", False)
]),
```

**Step 4: Commit**

```bash
git add src/db/sync.py
git commit -m "feat(sync): write DataQualitySnapshot and exclude legacy from high_risk_count"
```

---

## Task 5: `scheduler.py` — 固定工单拉取起点为 2026-01-01

**Files:**
- Modify: `src/api/scheduler.py`

**Step 1: 修改 `run_inventory_and_orders()` 中的 `--start` 参数**

将：
```python
subprocess.run([
    "python3", "src/scrapers/shop_order_scraper.py",
    "--start", (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
], cwd=BASE_DIR, check=True)
```

改为：
```python
subprocess.run([
    "python3", "src/scrapers/shop_order_scraper.py",
    "--start", "2026-01-01 00:00:00"
], cwd=BASE_DIR, check=True)
```

**Step 2: Commit**

```bash
git add src/api/scheduler.py
git commit -m "fix(scheduler): set IMES shop order start date to fixed 2026-01-01"
```

---

## Task 6: `nwms_scraper.py` — 新增 `--start` 过滤参数

**Files:**
- Modify: `src/scrapers/nwms_scraper.py`

**Step 1: 读取 nwms_scraper.py 了解当前参数解析结构**

先阅读文件确认 argparse 的位置，然后新增 `--start` 参数：

```python
parser.add_argument(
    "--start",
    default="2026-01-01",
    help="只拉取 ppStartTime >= 此日期的备料单（默认 2026-01-01）"
)
```

**Step 2: 在头表拉取逻辑中应用日期过滤**

在拉取备料单头表的循环中，过滤 `ppStartTime < args.start` 的记录：

```python
start_date = args.start  # 如 "2026-01-01"
# 在处理每条备料单时：
pp_start = row.get("ppStartTime", "") or ""
if pp_start and pp_start[:10] < start_date:
    continue  # 跳过过早的备料单
```

**Step 3: 验证（测试模式）**

```bash
python3 src/scrapers/nwms_scraper.py --test --start 2026-01-01
```

Expected: 输出的备料单均为 2026-01-01 之后的记录。

**Step 4: Commit**

```bash
git add src/scrapers/nwms_scraper.py
git commit -m "feat(nwms): add --start date filter to scraper (default 2026-01-01)"
```

---

## 验收清单

- [ ] `data_quality_snapshots` 表已在 SQLite 中创建
- [ ] `alert_report_snapshots` 表新增 `is_legacy` 列
- [ ] 每次 `run_and_sync()` 后，`data_quality_snapshots` 有新记录
- [ ] `high_risk_count` KPI 不再统计历史遗留数据
- [ ] NWMS 爬虫默认只拉 2026-01-01 之后的备料单
- [ ] 进场审计只保留关联工单在 IMES 中存在的行
- [ ] `python3 src/db/sync.py` 独立运行无报错
- [ ] `nwms_match_rate` 和 `alert_match_rate` 在数据库中有合理值（非 0 非 100）
