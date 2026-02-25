# Phase 8 — 线边仓物料用途状态标签 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对线边仓每条物料动态标注「当前生产 / 即将生产 / 已完工待退 / 下工单复用」，在仪表盘和明细页以彩色 Chip 展示。

**Architecture:**
- 新增 `InventoryStatusSnapshot` 表存全量线边仓快照（含 `wo_status_label`），供明细页离场审计 Tab 使用
- `AlertReportSnapshot`（退料预警）新增 `reuse_label` 列，标记已完工物料是否被在制/待开工工单复用
- `build_report.py` 新增 `build_inventory_status()` 函数处理全量库存，并在现有退料预警行中注入 `reuse_label`

**Tech Stack:** Python + SQLite/SQLAlchemy + FastAPI + React + TailwindCSS

---

## 工单状态映射

| statusDesc | wo_status_label | Chip 颜色 |
|---|---|---|
| `Se ha iniciado la construcción` | `current` | 🟢 绿色 |
| `Se puede emitir` | `upcoming` | 🔵 蓝色 |
| `Completado` / `已完成` | `completed` | 🟠 橙色 |
| 找不到工单 / 其他 | `""` | 不显示 |

| reuse_label | 含义 | 徽章 |
|---|---|---|
| `reuse_current` | 已完工但物料被当前在制工单BOM包含 | 🔄 当前工单复用 |
| `reuse_upcoming` | 已完工但物料被待开工工单BOM包含 | 🔄 下工单复用 |
| `""` | 无复用，正常退料 | 不显示 |

---

## Task 1: DB Model — 新增列和新表

**Files:**
- Modify: `src/db/models.py`

**Step 1: 在 `AlertReportSnapshot` 末尾新增 `reuse_label` 列**

在 `barcode_list` 列下方追加：
```python
reuse_label = Column(String(20), default="")   # reuse_current / reuse_upcoming / ""
```

**Step 2: 在 `IssueAuditSnapshot` 类之前新增 `InventoryStatusSnapshot` 类**

```python
class InventoryStatusSnapshot(Base):
    __tablename__ = "inventory_status_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    shop_order      = Column(String(50), index=True)
    material_code   = Column(String(50), index=True)
    material_desc   = Column(Text)
    warehouse       = Column(String(100))
    unit            = Column(String(20))
    actual_inventory= Column(Float, default=0.0)
    barcode_count   = Column(Integer, default=0)
    order_status    = Column(String(50))          # 原始工单状态字段值
    wo_status_label = Column(String(20), default="")  # current/upcoming/completed/""
    receive_time    = Column(String(50))
    is_legacy       = Column(Integer, default=0)
    barcode_list    = Column(Text, default="[]")
    reuse_label     = Column(String(20), default="")  # reuse_current/reuse_upcoming/""
    theory_remain   = Column(Float, default=0.0)      # 仅completed行有意义
    deviation       = Column(Float, default=0.0)      # 仅completed行有意义

    __table_args__ = (
        Index('idx_invstatus_batch_order_mat', 'batch_id', 'shop_order', 'material_code'),
    )
```

**Step 3: 更新 sync.py 顶部 import**

`src/db/sync.py` 第4行，添加 `InventoryStatusSnapshot`：
```python
from src.db.models import KPIHistory, AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot, InventoryStatusSnapshot
```

---

## Task 2: DB Migration — 幂等脚本

**Files:**
- Modify: `tools/migrate_db.py`

在文件末尾 `conn.close()` 之前追加：

```python
# Phase 8 - Step 1: alert_report_snapshots 新增 reuse_label 列
try:
    cursor.execute("ALTER TABLE alert_report_snapshots ADD COLUMN reuse_label VARCHAR(20) DEFAULT '';")
    conn.commit()
    print("[MIGRATE] ✅ alert_report_snapshots.reuse_label 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  alert_report_snapshots.reuse_label 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

# Phase 8 - Step 2: 新建 inventory_status_snapshots 表
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_status_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id VARCHAR(50) NOT NULL,
            timestamp DATETIME,
            shop_order VARCHAR(50),
            material_code VARCHAR(50),
            material_desc TEXT,
            warehouse VARCHAR(100),
            unit VARCHAR(20),
            actual_inventory REAL DEFAULT 0.0,
            barcode_count INTEGER DEFAULT 0,
            order_status VARCHAR(50),
            wo_status_label VARCHAR(20) DEFAULT '',
            receive_time VARCHAR(50),
            is_legacy INTEGER DEFAULT 0,
            barcode_list TEXT DEFAULT '[]',
            reuse_label VARCHAR(20) DEFAULT '',
            theory_remain REAL DEFAULT 0.0,
            deviation REAL DEFAULT 0.0
        );
    """)
    conn.commit()
    print("[MIGRATE] ✅ inventory_status_snapshots 表已就绪")
except sqlite3.OperationalError as e:
    print(f"[MIGRATE] ❌ 错误: {e}")
```

**Step 3: 运行迁移**

```bash
cd /home/chenweijie/projects/matetial_monitor
PYTHONPATH=. python3 tools/migrate_db.py
```

期望输出末尾包含：
```
[MIGRATE] ✅ alert_report_snapshots.reuse_label 列新增成功
[MIGRATE] ✅ inventory_status_snapshots 表已就绪
[MIGRATE] 迁移完成
```

---

## Task 3: build_report.py — 全量库存状态分析

**Files:**
- Modify: `src/analysis/build_report.py`

### Step 1: 在文件顶部新增状态常量（`COMPLETED_STATUSES` 下方）

```python
CURRENT_STATUSES  = {"Se ha iniciado la construcción"}
UPCOMING_STATUSES = {"Se puede emitir"}

def _wo_status_label(status_desc: str) -> str:
    if status_desc in CURRENT_STATUSES:
        return "current"
    if status_desc in UPCOMING_STATUSES:
        return "upcoming"
    if status_desc in COMPLETED_STATUSES:
        return "completed"
    return ""
```

### Step 2: 新增 `build_inventory_status()` 函数

在 `build_return_alert()` 函数之后、`build_issue_audit()` 之前插入：

```python
def build_inventory_status(orders, bom_index, inventory):
    """
    全量线边仓物料状态分析（A 功能）：
    - 处理所有有工单关联的库存行（不按完工过滤）
    - 赋予 wo_status_label（current/upcoming/completed/""）
    - 对 completed 行赋予 reuse_label（是否被在制/待开工工单BOM复用）
    """
    # 构建在制/待开工工单的 BOM 物料集合（用于 reuse_label 判断）
    current_bom_mats  = set()
    upcoming_bom_mats = set()
    for wo, order in orders.items():
        status = order.get("statusDesc", "")
        if status in CURRENT_STATUSES:
            for (bom_wo, mat) in bom_index:
                if bom_wo == wo:
                    current_bom_mats.add(mat)
        elif status in UPCOMING_STATUSES:
            for (bom_wo, mat) in bom_index:
                if bom_wo == wo:
                    upcoming_bom_mats.add(mat)

    results = []
    for (wo, mat), inv in inventory.items():
        order = orders.get(wo)
        if not order:
            continue  # 工单不在 IMES 窗口内，跳过

        status_desc = order.get("statusDesc", "")
        label = _wo_status_label(status_desc)

        bom = bom_index.get((wo, mat))
        qty_done    = float(order.get("qtyDone") or 0)
        qty_ordered = float(order.get("qtyOrdered") or 0)
        if bom:
            unit_qty   = float(bom.get("qty") or 0)
            sum_qty    = float(bom.get("sumQty") or 0)
            theory_rem = sum_qty - qty_done * unit_qty
        else:
            unit_qty = sum_qty = theory_rem = 0.0

        actual_inv = inv["qty"]
        deviation  = round(actual_inv - theory_rem, 2) if sum_qty > 0 else 0.0

        # reuse_label：仅对 completed 行判断
        reuse = ""
        if label == "completed":
            if mat in current_bom_mats:
                reuse = "reuse_current"
            elif mat in upcoming_bom_mats:
                reuse = "reuse_upcoming"

        results.append({
            "工单号":        wo,
            "物料编号":      mat,
            "物料描述":      inv["desc"],
            "线边仓":        inv["warehouse"],
            "单位":          inv["unit"],
            "实际库存(合计)": round(actual_inv, 2),
            "条码数":        inv["barcodes"],
            "barcode_list":  inv.get("barcode_list", []),
            "工单状态":      status_desc,
            "wo_status_label": label,
            "接收时间":      inv["receive_time"],
            "is_legacy":     _is_legacy(inv["receive_time"]),
            "理论余料":      round(theory_rem, 2),
            "偏差(实际-理论)": deviation,
            "reuse_label":   reuse,
        })

    results.sort(key=lambda x: (x["wo_status_label"], -x["实际库存(合计)"]))
    return results
```

### Step 3: 在 `build_return_alert()` 结果中注入 `reuse_label`

在 `build_return_alert()` 函数中，已有 `current_bom_mats` / `upcoming_bom_mats` 的构建逻辑需复用。修改方式：

在 `build_return_alert()` 函数体开头，复用同样逻辑构建两个集合（可调用公共helper），然后在每条 `results.append(...)` 末尾加入：

```python
# 在 results.append({...}) 内的字段列表末尾追加：
"reuse_label": _calc_reuse_label(mat, current_bom_mats, upcoming_bom_mats),
```

并在函数体开头（`results = []` 之后）添加：
```python
current_bom_mats, upcoming_bom_mats = _build_reuse_sets(orders, bom_index)
```

### Step 4: 提取公共 helper（消除重复）

在 `_wo_status_label()` 下方添加：

```python
def _build_reuse_sets(orders, bom_index):
    """构建在制/待开工工单的 BOM 物料集合"""
    current_bom_mats  = set()
    upcoming_bom_mats = set()
    for wo, order in orders.items():
        status = order.get("statusDesc", "")
        target = None
        if status in CURRENT_STATUSES:
            target = current_bom_mats
        elif status in UPCOMING_STATUSES:
            target = upcoming_bom_mats
        if target is not None:
            for (bom_wo, mat) in bom_index:
                if bom_wo == wo:
                    target.add(mat)
    return current_bom_mats, upcoming_bom_mats

def _calc_reuse_label(mat: str, current_bom_mats: set, upcoming_bom_mats: set) -> str:
    if mat in current_bom_mats:
        return "reuse_current"
    if mat in upcoming_bom_mats:
        return "reuse_upcoming"
    return ""
```

### Step 5: `run()` 函数末尾调用并返回新数据

在 `run()` 函数 `return alert, issue_audit, quality_stats` 之前添加：

```python
    print("\n─── 全量库存状态分析（Phase 8）────────────────────")
    inventory_status = build_inventory_status(orders, bom_index, inventory)
    print(f"  全量库存行: {len(inventory_status)} 组")
    current_cnt  = sum(1 for r in inventory_status if r["wo_status_label"] == "current")
    upcoming_cnt = sum(1 for r in inventory_status if r["wo_status_label"] == "upcoming")
    completed_cnt= sum(1 for r in inventory_status if r["wo_status_label"] == "completed")
    print(f"  当前生产: {current_cnt}  即将生产: {upcoming_cnt}  已完工待退: {completed_cnt}")
```

然后修改 return：
```python
    return alert, issue_audit, quality_stats, inventory_status
```

---

## Task 4: sync.py — 同步全量库存状态

**Files:**
- Modify: `src/db/sync.py`

### Step 1: 更新 `build_report_run()` 调用，解包新返回值

第147行：
```python
# 旧
alert_rows, issue_rows, quality_stats = build_report_run()
# 新
alert_rows, issue_rows, quality_stats, inventory_status_rows = build_report_run()
```

### Step 2: 在 `save_to_db()` 签名中新增 `inventory_status_rows` 参数

```python
def save_to_db(alert_rows, issue_rows, quality_stats, inventory_status_rows, session, batch_id):
```

### Step 3: 在 `save_to_db()` 中，写 alert 快照时传入 `reuse_label`

第82行 `AlertReportSnapshot(...)` 内 `barcode_list=...` 后追加：
```python
reuse_label=safe_str(r.get("reuse_label", "")),
```

### Step 4: 在 `save_to_db()` 写 Issue 快照之后（# 3 之后）新增写全量库存快照的块

```python
    # 3b. 写入全量库存状态快照（Phase 8）
    if inventory_status_rows:
        inv_inserts = []
        for r in inventory_status_rows:
            inv_inserts.append(InventoryStatusSnapshot(
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
                wo_status_label=safe_str(r.get("wo_status_label")),
                receive_time=safe_str(r.get("接收时间")),
                is_legacy=1 if r.get("is_legacy") else 0,
                barcode_list=json.dumps(r.get("barcode_list", []), ensure_ascii=False),
                reuse_label=safe_str(r.get("reuse_label")),
                theory_remain=safe_float(r.get("理论余料")),
                deviation=safe_float(r.get("偏差(实际-理论)")),
            ))
        session.bulk_save_objects(inv_inserts)
```

### Step 5: `purge_old_batches()` 的 Model 列表加入新表

```python
for Model in [AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot, KPIHistory, InventoryStatusSnapshot]:
```

### Step 6: 更新 `run_and_sync()` 调用

```python
save_to_db(alert_rows, issue_rows, quality_stats, inventory_status_rows, db, batch_id)
```

---

## Task 5: API — 新增接口 + 更新现有接口

**Files:**
- Modify: `src/api/main.py`

### Step 1: import 新增 InventoryStatusSnapshot

第11行：
```python
from src.db.models import KPIHistory, AlertReportSnapshot, IssueAuditSnapshot, DataQualitySnapshot, InventoryStatusSnapshot
```

### Step 2: 更新 `get_alerts_top10()` 返回字段（新增 `reuse_label`）

在 return 列表的每个 dict 末尾追加：
```python
"reuse_label": r.reuse_label or "",
```

### Step 3: 更新 `get_alerts_list()` 返回字段（新增 `reuse_label`）

在 return 列表的每个 dict 末尾追加：
```python
"reuse_label": r.reuse_label or "",
```

### Step 4: 新增 `/api/inventory/status` 接口

在 `/api/quality/latest` 接口之前插入：

```python
@app.get("/api/inventory/status")
def get_inventory_status(batch_id: str = "", q: str = "", label: str = ""):
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

        stmt = stmt.order_by(
            InventoryStatusSnapshot.wo_status_label,
            desc(InventoryStatusSnapshot.actual_inventory)
        )
        rows = db.execute(stmt).scalars().all()

        def _calc_aging(rt) -> float:
            try:
                from datetime import datetime as dt
                s = str(rt).strip().split(" ")[0].replace("/", "-")
                parts = s.split("-")
                if len(parts) == 3:
                    s = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                return round((dt.utcnow() - dt.strptime(s, "%Y-%m-%d")).total_seconds() / 86400, 1)
            except Exception:
                return -1.0

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
                "aging_days":       _calc_aging(r.receive_time),
                "is_legacy":        r.is_legacy,
                "reuse_label":      r.reuse_label or "",
                "theory_remain":    r.theory_remain,
                "deviation":        r.deviation,
            }
            for r in rows
        ]
    finally:
        db.close()
```

---

## Task 6: 前端 — 公共组件 WoStatusChip

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/DetailPage.tsx`

### Step 1: Dashboard.tsx — 在文件顶部 AgingBadgeSmall 下方新增 WoStatusChip 组件

```tsx
function WoStatusChip({ label, reuse }: { label: string; reuse?: string }) {
    if (reuse === 'reuse_current') return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#14532d55', color: '#4ade80', border: '1px solid #16a34a' }}>
            🔄 当前工单复用
        </span>
    )
    if (reuse === 'reuse_upcoming') return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#1e3a5f55', color: '#93c5fd', border: '1px solid #3b82f6' }}>
            🔄 下工单复用
        </span>
    )
    if (label === 'current') return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#14532d55', color: '#4ade80', border: '1px solid #16a34a' }}>
            🟢 当前生产
        </span>
    )
    if (label === 'upcoming') return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#1e3a5f55', color: '#93c5fd', border: '1px solid #3b82f6' }}>
            🔵 即将生产
        </span>
    )
    if (label === 'completed') return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#7c2d1255', color: '#fb923c', border: '1px solid #c2410c' }}>
            🟠 已完工待退
        </span>
    )
    return null
}
```

### Step 2: Dashboard.tsx — 更新 `AlertTop` interface

```tsx
interface AlertTop {
    shop_order: string;
    material_code: string;
    material_desc: string;
    warehouse: string;
    actual_inventory: number;
    unit: string;
    barcode_count: number;
    aging_days: number;
    reuse_label: string;   // 新增
}
```

### Step 3: Dashboard.tsx — 退料预警表格新增「物料状态」列

找到退料预警表格的 `<thead>` 部分，在「库龄」列之后新增列头：
```tsx
<th className="px-3 py-2 text-left text-xs text-gray-400 font-medium whitespace-nowrap">物料状态</th>
```

在对应的 `<tbody>` 数据行中，在库龄列单元格之后新增：
```tsx
<td className="px-3 py-2">
    <WoStatusChip label="completed" reuse={row.reuse_label} />
</td>
```

> 注：退料预警列表均为 completed 状态，只显示 reuse_label 徽章（若有）或橙色已完工待退 Chip

---

## Task 7: 前端 DetailPage — 离场审计 Tab 全量展示

**Files:**
- Modify: `frontend/src/pages/DetailPage.tsx`

### Step 1: 新增 interfaces

```tsx
interface InventoryStatusRow {
    shop_order: string; material_code: string; material_desc: string
    warehouse: string; actual_inventory: number; barcode_count: number;
    unit: string; aging_days: number; barcode_list: string[];
    wo_status_label: string; reuse_label: string;
    order_status: string; is_legacy: number;
    theory_remain: number; deviation: number;
}
```

### Step 2: 新增 state

```tsx
const [invStatusRows, setInvStatusRows] = useState<InventoryStatusRow[]>([])
const [labelFilter, setLabelFilter] = useState<string>('all')
```

### Step 3: 新增 WoStatusChip 组件（复制自 Dashboard，与 AgingBadge 同级位置）

（同 Task 6 Step 1 代码）

### Step 4: 新增数据加载逻辑

在现有 `alertRows` 加载函数中，追加对 `/api/inventory/status` 的请求：
```tsx
const resInv = await axios.get('/api/inventory/status', { params: { batch_id: batchId, q: query } })
setInvStatusRows(resInv.data)
```

### Step 5: 离场审计 Tab 顶部新增 label 筛选 Chips

在现有库龄 Chip 筛选行之后，新增一行：
```tsx
{/* 物料用途状态筛选 */}
<div className="flex gap-2 flex-wrap">
    {[
        { key: 'all',           label: '全部' },
        { key: 'current',       label: '🟢 当前生产' },
        { key: 'upcoming',      label: '🔵 即将生产' },
        { key: 'completed',     label: '🟠 已完工待退' },
        { key: 'reuse_current', label: '🔄 当前工单复用' },
        { key: 'reuse_upcoming',label: '🔄 下工单复用' },
    ].map(c => (
        <button key={c.key}
            onClick={() => setLabelFilter(c.key)}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                labelFilter === c.key
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700'
            }`}
        >{c.label}</button>
    ))}
</div>
```

### Step 6: 离场审计 Tab 表格切换为 `invStatusRows` 数据源

将现有 `alertRows` 表格改为渲染 `invStatusRows`，过滤逻辑：
```tsx
const filteredInv = invStatusRows.filter(r => {
    if (labelFilter === 'all') return true
    if (labelFilter === 'reuse_current') return r.reuse_label === 'reuse_current'
    if (labelFilter === 'reuse_upcoming') return r.reuse_label === 'reuse_upcoming'
    return r.wo_status_label === labelFilter
}).filter(r => {
    // 库龄 chip 过滤（仅对 completed 行有意义，其他保留）
    if (alertChip === 'all') return true
    if (r.aging_days < 0) return false
    if (alertChip === 'le3')   return r.aging_days <= 3
    if (alertChip === 'd3_7')  return r.aging_days > 3 && r.aging_days <= 7
    if (alertChip === 'd7_14') return r.aging_days > 7 && r.aging_days <= 14
    if (alertChip === 'gt14')  return r.aging_days > 14
    return true
})
```

### Step 7: 表格新增「物料状态」列

在「库龄」列之后新增：

表头：
```tsx
<th className="px-3 py-2 text-left text-xs text-gray-400 font-medium whitespace-nowrap">物料状态</th>
```

数据行：
```tsx
<td className="px-3 py-2">
    <WoStatusChip label={row.wo_status_label} reuse={row.reuse_label} />
</td>
```

---

## Task 8: 手动测试验证

```bash
# 1. 运行迁移（已在 Task 2 完成）
PYTHONPATH=. python3 tools/migrate_db.py

# 2. 触发一次完整分析同步
PYTHONPATH=. python3 -m src.db.sync

# 3. 验证新接口
curl "http://localhost:8000/api/inventory/status?label=current" | python3 -m json.tool | head -50
curl "http://localhost:8000/api/inventory/status?label=upcoming" | python3 -m json.tool | head -50
curl "http://localhost:8000/api/alerts/top10" | python3 -m json.tool | head -30

# 4. 启动前端开发服务器
cd frontend && pnpm run dev
# 访问 http://localhost:5173 验证：
# - 仪表盘退料预警列表有「物料状态」列
# - 明细页离场审计 Tab 有 6 个状态筛选 Chip
# - 各 Chip 筛选结果正确
```

---

## Task 9: 提交

```bash
git add src/db/models.py tools/migrate_db.py src/analysis/build_report.py \
        src/db/sync.py src/api/main.py \
        frontend/src/pages/Dashboard.tsx frontend/src/pages/DetailPage.tsx

git commit -m "feat: Phase 8 — 线边仓物料用途状态标签（当前/即将/复用/已完工待退）"
```

---

## 变更文件汇总

| 文件 | 改动类型 |
|---|---|
| `src/db/models.py` | AlertReportSnapshot 新增 reuse_label；新增 InventoryStatusSnapshot 表 |
| `tools/migrate_db.py` | 新增两段迁移语句 |
| `src/analysis/build_report.py` | 新增常量+helper；新增 build_inventory_status()；alert 行注入 reuse_label；run() 返回新数据 |
| `src/db/sync.py` | 同步 reuse_label；写入 InventoryStatusSnapshot；purge 新表 |
| `src/api/main.py` | alerts/top10 + alerts/list 返回 reuse_label；新增 /api/inventory/status |
| `frontend/src/pages/Dashboard.tsx` | 新增 WoStatusChip；退料预警表新增物料状态列 |
| `frontend/src/pages/DetailPage.tsx` | 新增 WoStatusChip；新增状态筛选 Chips；离场审计切换为全量数据源 |
