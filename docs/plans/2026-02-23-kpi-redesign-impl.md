# KPI 重构实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将仪表盘 KPI 从「偏差驱动」重构为「完工有库存即预警」，新增 5 张卡片、库龄色带分布、明细页库龄列与 Chip 筛选。

**Architecture:** 后端新增 3 个 KPI 字段 + 库龄分布数组，接口扩展向下兼容；前端 Dashboard 重构 5 卡布局 + 色带，DetailPage 离场 Tab 移除偏差列、新增库龄列与筛选。

**Tech Stack:** Python + SQLAlchemy + FastAPI / React 18 + TypeScript + Tailwind CSS

---

## Task 1: 后端 — `KPIHistory` 新增 3 个字段

**Files:**
- Modify: `src/db/models.py`

**Step 1: 在 `KPIHistory` 类末尾新增字段**

在 `avg_aging_hours` 之后追加：

```python
# Phase 3 KPI 重构：三层分类计数
confirmed_alert_count   = Column(Integer, default=0)  # 当期退料预警（完工+已匹配+仍有库存）
unmatched_current_count = Column(Integer, default=0)  # 工单范围外库存（接收≥2026但工单未匹配）
legacy_count            = Column(Integer, default=0)  # 历史遗留库存（接收<2026或为空）
```

**Step 2: 验证建表（幂等）**

```bash
export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
python3 -c "
from src.db.database import engine, Base
from src.db import models
Base.metadata.create_all(bind=engine)
print('OK - columns added')
"
```

Expected: 输出 `OK - columns added`，无报错。

**Step 3: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add confirmed_alert/unmatched_current/legacy_count to KPIHistory"
```

---

## Task 2: 后端 — `build_report.py` 统计三层计数 + 库龄分布

**Files:**
- Modify: `src/analysis/build_report.py`

**Step 1: 在 `run()` 函数中新增三层计数统计**

在 `alert = build_return_alert(...)` 之后，现有 `quality_stats` 构造之前插入：

```python
from datetime import datetime as dt

NOW = dt.now()

def _aging_days(receive_time_str: str) -> float:
    """计算库龄天数，无法解析时返回 -1"""
    d = _parse_date(receive_time_str)
    if d is None:
        return -1.0
    return (NOW - d).total_seconds() / 86400

# 三层分类
confirmed_alerts = [
    r for r in alert
    if not r.get("is_legacy")
    and r.get("工单号") in orders          # 工单已匹配
]
unmatched_current = [
    (wo, mat) for (wo, mat), inv in inventory.items()
    if not _is_legacy(inv["receive_time"])  # 接收时间 >= 2026
    and wo not in orders                   # 但工单未匹配
]
legacy_items = [
    (wo, mat) for (wo, mat), inv in inventory.items()
    if _is_legacy(inv["receive_time"])
]

# 库龄分布（仅统计 confirmed_alerts）
aging_dist = {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}
aging_hours_list = []
for r in confirmed_alerts:
    days = _aging_days(r.get("接收时间", ""))
    if days < 0:
        continue
    aging_hours_list.append(days * 24)
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

avg_aging_current = round(
    sum(aging_hours_list) / len(aging_hours_list), 1
) if aging_hours_list else 0.0
```

**Step 2: 将新统计写入 `quality_stats`**

在现有 `quality_stats` 字典中新增：

```python
quality_stats.update({
    "confirmed_alert_count":   len(confirmed_alerts),
    "unmatched_current_count": len(unmatched_current),
    "legacy_count":            len(legacy_items),
    "avg_aging_hours_current": avg_aging_current,
    "aging_distribution":      aging_dist,
})
```

**Step 3: 为 `alert` 行新增 `aging_days` 字段**

在 `build_return_alert()` 的 `results.append({...})` 中新增：

```python
"aging_days": round((dt.now() - _parse_date(inv["receive_time"])).total_seconds() / 86400, 1)
              if _parse_date(inv["receive_time"]) else -1,
```

**Step 4: 手动验证**

```bash
python3 src/analysis/build_report.py
```

Expected: 输出中新增类似：
```
confirmed_alert_count: N
unmatched_current_count: N
legacy_count: 34
aging_dist: {"le1": N, ...}
```

**Step 5: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat(analysis): add 3-tier KPI counts, aging distribution, and aging_days field"
```

---

## Task 3: 后端 — `sync.py` 写入新字段，`avg_aging_hours` 改用当期口径

**Files:**
- Modify: `src/db/sync.py`

**Step 1: 在 `save_to_db()` 的 `KPIHistory` 写入中新增字段**

```python
kpi = KPIHistory(
    batch_id=batch_id,
    timestamp=ts,
    # 旧字段保留（趋势图历史数据不断层）
    alert_group_count=len(alert_rows),
    high_risk_count=len([r for r in alert_rows
                         if safe_float(r.get("偏差(实际-理论)")) > 0.01
                         and not r.get("is_legacy")]),
    over_issue_lines=len([r for r in issue_rows
                          if safe_float(r.get("超发量")) > 0.01]) if issue_rows else 0,
    # avg_aging_hours 改用当期已核实口径
    avg_aging_hours=quality_stats.get("avg_aging_hours_current", 0.0),
    # 新增三层计数
    confirmed_alert_count=quality_stats.get("confirmed_alert_count", 0),
    unmatched_current_count=quality_stats.get("unmatched_current_count", 0),
    legacy_count=quality_stats.get("legacy_count", 0),
)
```

**Step 2: 验证同步写入**

```bash
python3 src/db/sync.py
```

Expected: 输出 `[DB] 快照写入完成`，查询 SQLite 确认新字段有值：

```bash
python3 -c "
from src.db.database import SessionLocal
from src.db.models import KPIHistory
from sqlalchemy import desc, select
db = SessionLocal()
r = db.execute(select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)).scalar_one()
print(r.confirmed_alert_count, r.unmatched_current_count, r.legacy_count, r.avg_aging_hours)
db.close()
"
```

Expected: 四个数字均非 None，且 `legacy_count` ≈ 34。

**Step 3: Commit**

```bash
git add src/db/sync.py
git commit -m "feat(sync): write new 3-tier KPI counts and switch avg_aging to current-only scope"
```

---

## Task 4: 后端 — `main.py` 扩展 `/api/kpi/summary` 和 `/api/alerts/list`

**Files:**
- Modify: `src/api/main.py`

**Step 1: 扩展 `/api/kpi/summary` 返回值**

在现有返回字典中追加：

```python
return {
    # 旧字段保留
    "batch_id": latest_kpi.batch_id,
    "timestamp": latest_kpi.timestamp.isoformat(),
    "alert_group_count": latest_kpi.alert_group_count,
    "high_risk_count": latest_kpi.high_risk_count,
    "over_issue_lines": latest_kpi.over_issue_lines,
    "avg_aging_hours": latest_kpi.avg_aging_hours,
    # 新增字段
    "confirmed_alert_count":   latest_kpi.confirmed_alert_count or 0,
    "unmatched_current_count": latest_kpi.unmatched_current_count or 0,
    "legacy_count":            latest_kpi.legacy_count or 0,
}
```

**Step 2: 新增 `/api/kpi/aging-distribution` 接口**

```python
@app.get("/api/kpi/aging-distribution")
def get_aging_distribution():
    """返回最新批次当期已核实物料的库龄分布"""
    db = SessionLocal()
    try:
        latest = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        if not latest:
            return {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}

        from datetime import datetime as dt
        now = dt.utcnow()
        rows = db.execute(
            select(AlertReportSnapshot)
            .where(AlertReportSnapshot.batch_id == latest.batch_id)
            .where(AlertReportSnapshot.is_legacy == 0)
        ).scalars().all()

        dist = {"le1": 0, "d1_3": 0, "d3_7": 0, "d7_14": 0, "d14_30": 0, "gt30": 0}
        for r in rows:
            try:
                recv = dt.strptime(str(r.receive_time)[:10], "%Y-%m-%d")
                days = (now - recv).days
            except (ValueError, TypeError):
                continue
            if days <= 1:   dist["le1"]   += 1
            elif days <= 3: dist["d1_3"]  += 1
            elif days <= 7: dist["d3_7"]  += 1
            elif days <= 14: dist["d7_14"] += 1
            elif days <= 30: dist["d14_30"] += 1
            else:            dist["gt30"]  += 1
        return dist
    finally:
        db.close()
```

**Step 3: 扩展 `/api/alerts/list` 返回值**

在现有返回字典中追加 `aging_days` 和 `unit`：

```python
return [
    {
        "shop_order": r.shop_order,
        "material_code": r.material_code,
        "material_desc": r.material_desc,
        "warehouse": r.warehouse,
        "actual_inventory": r.actual_inventory,
        "unit": r.unit,                         # 新增
        "barcode_count": r.barcode_count,        # 新增
        "aging_days": _calc_aging_days(r.receive_time),  # 新增
        # 保留但不在前台主展示（供导出备用）
        "theory_remain": r.theory_remain,
        "deviation": r.deviation,
    }
    for r in rows
]
```

在文件顶部添加辅助函数：

```python
def _calc_aging_days(receive_time_str) -> float:
    try:
        from datetime import datetime as dt
        d = dt.strptime(str(receive_time_str)[:10], "%Y-%m-%d")
        return round((dt.utcnow() - d).total_seconds() / 86400, 1)
    except (ValueError, TypeError):
        return -1.0
```

**Step 4: 验证接口**

```bash
uvicorn src.api.main:app --reload &
curl http://localhost:8000/api/kpi/summary | python3 -m json.tool
curl http://localhost:8000/api/kpi/aging-distribution | python3 -m json.tool
curl "http://localhost:8000/api/alerts/list" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0] if d else 'empty')"
```

Expected: `summary` 含 `confirmed_alert_count`，`aging-distribution` 含 6 个键，`alerts/list` 首条含 `aging_days` 和 `unit`。

**Step 5: Commit**

```bash
git add src/api/main.py
git commit -m "feat(api): extend kpi/summary, add aging-distribution endpoint, extend alerts/list"
```

---

## Task 5: 前端 — Dashboard 重构为 5 张卡片 + 库龄色带

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: 更新 `KPISummary` interface**

```typescript
interface KPISummary {
    batch_id: string;
    timestamp: string;
    // 旧字段保留（趋势图使用）
    alert_group_count: number;
    high_risk_count: number;
    over_issue_lines: number;
    avg_aging_hours: number;
    // 新增
    confirmed_alert_count: number;
    unmatched_current_count: number;
    legacy_count: number;
}

interface AgingDist {
    le1: number; d1_3: number; d3_7: number;
    d7_14: number; d14_30: number; gt30: number;
}
```

**Step 2: 新增 `agingDist` state，在 `fetchData` 中拉取**

```typescript
const [agingDist, setAgingDist] = useState<AgingDist | null>(null)

// fetchData 中新增：
const agingRes = await axios.get<AgingDist>('/api/kpi/aging-distribution')
setAgingDist(agingRes.data)
```

**Step 3: 替换 KPI 卡片区（4卡 → 5卡）**

将原有 `grid-cols-4` 区块替换为：

```tsx
<div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
    {/* 卡片1：当期退料预警 */}
    <div className="glass-panel p-5 border-l-4 border-l-red-500 animate-fade-in">
        <h3 className="text-gray-400 text-xs font-medium mb-1">当期退料预警</h3>
        <div className="text-3xl font-bold text-white">{kpi?.confirmed_alert_count ?? '-'}</div>
        <p className="text-xs text-gray-500 mt-2">完工工单仍有线边仓库存</p>
    </div>
    {/* 卡片2：工单范围外 */}
    <div className="glass-panel p-5 border-l-4 border-l-orange-500 animate-fade-in" style={{animationDelay:'80ms'}}>
        <h3 className="text-gray-400 text-xs font-medium mb-1">工单范围外库存</h3>
        <div className="text-3xl font-bold text-orange-400">{kpi?.unmatched_current_count ?? '-'}</div>
        <p className="text-xs text-gray-500 mt-2">接收≥2026，工单超出监控窗口</p>
    </div>
    {/* 卡片3：历史遗留 */}
    <div className="glass-panel p-5 border-l-4 border-l-gray-500 animate-fade-in" style={{animationDelay:'160ms'}}>
        <h3 className="text-gray-400 text-xs font-medium mb-1">历史遗留库存</h3>
        <div className="text-3xl font-bold text-gray-400">{kpi?.legacy_count ?? '-'}</div>
        <p className="text-xs text-gray-500 mt-2">接收&lt;2026或为空，不纳入预警</p>
    </div>
    {/* 卡片4：进场超发 */}
    <div className="glass-panel p-5 border-l-4 border-l-yellow-500 animate-fade-in" style={{animationDelay:'240ms'}}>
        <h3 className="text-gray-400 text-xs font-medium mb-1">进场超发预警</h3>
        <div className="text-3xl font-bold text-yellow-500">{kpi?.over_issue_lines ?? '-'}</div>
        <p className="text-xs text-gray-500 mt-2">NWMS 实际发料量 &gt; 计划量</p>
    </div>
    {/* 卡片5：当期平均库龄 */}
    <div className="glass-panel p-5 border-l-4 border-l-purple-500 animate-fade-in" style={{animationDelay:'320ms'}}>
        <h3 className="text-gray-400 text-xs font-medium mb-1">当期平均库龄</h3>
        <div className="text-3xl font-bold text-purple-400">
            {kpi?.avg_aging_hours ?? '-'} <span className="text-lg">h</span>
        </div>
        <p className="text-xs text-gray-500 mt-2">仅统计当期已核实退料物料</p>
    </div>
</div>
```

**Step 4: 在 KPI 卡片下方新增库龄色带**

```tsx
{agingDist && (
    <div className="glass-panel p-4 mb-6">
        <h3 className="text-xs font-medium text-gray-400 mb-3">当期物料库龄分布</h3>
        <div className="flex gap-2 flex-wrap">
            {[
                { key: 'le1',   label: '≤1天',   color: 'bg-green-600',     text: 'text-green-400' },
                { key: 'd1_3',  label: '1-3天',   color: 'bg-emerald-600',   text: 'text-emerald-400' },
                { key: 'd3_7',  label: '3-7天',   color: 'bg-yellow-600',    text: 'text-yellow-400' },
                { key: 'd7_14', label: '7-14天',  color: 'bg-orange-600',    text: 'text-orange-400' },
                { key: 'd14_30',label: '14-30天', color: 'bg-orange-800',    text: 'text-orange-300' },
                { key: 'gt30',  label: '>30天',   color: 'bg-red-700',       text: 'text-red-400' },
            ].map(({ key, label, color, text }) => (
                <div
                    key={key}
                    className={`flex-1 min-w-[80px] ${color} bg-opacity-20 border border-opacity-30
                                rounded-lg p-3 text-center cursor-pointer hover:bg-opacity-30 transition-colors`}
                    onClick={() => window.location.href = `/detail?aging=${key}`}
                >
                    <div className={`text-xl font-bold ${text}`}>
                        {agingDist[key as keyof AgingDist]}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{label}</div>
                </div>
            ))}
        </div>
    </div>
)}
```

**Step 5: 验证页面**

```bash
cd frontend && npm run dev
```

浏览器访问 `http://localhost:5173`，检查：
- 5 张卡片正常显示，颜色正确
- 库龄色带 6 个色块正常渲染，数字不全为 0

**Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): redesign to 5 KPI cards and add aging distribution band"
```

---

## Task 6: 前端 — DetailPage 离场审计 Tab 重构

**Files:**
- Modify: `frontend/src/pages/DetailPage.tsx`

**Step 1: 更新 `AlertRow` interface**

```typescript
interface AlertRow {
    shop_order: string;
    material_code: string;
    material_desc: string;
    warehouse: string;
    actual_inventory: number;
    unit: string;           // 新增
    barcode_count: number;  // 新增
    aging_days: number;     // 新增
    // 保留但不展示
    theory_remain: number;
    deviation: number;
}
```

**Step 2: 新增库龄 badge 组件**

```typescript
function AgingBadge({ days }: { days: number }) {
    if (days < 0) return <span className="text-gray-500 text-xs">-</span>
    const cls =
        days <= 1  ? 'text-green-400' :
        days <= 3  ? 'text-emerald-400' :
        days <= 7  ? 'text-yellow-400' :
        days <= 14 ? 'text-orange-400' :
        days <= 30 ? 'text-orange-300' :
                     'text-red-400 font-bold'
    return <span className={`text-sm ${cls}`}>{Math.floor(days)}天</span>
}
```

**Step 3: 更新 Chip 筛选**

将旧的 `'all' | 'risk' | 'over' | 'under'` chip 类型改为：

```typescript
const [chip, setChip] = useState<'all' | 'le3' | 'd3_7' | 'd7_14' | 'gt14'>('all')
```

更新过滤逻辑：

```typescript
const filteredAlerts = alertRows.filter(r => {
    if (chip === 'le3')   return r.aging_days >= 0 && r.aging_days <= 3
    if (chip === 'd3_7')  return r.aging_days > 3  && r.aging_days <= 7
    if (chip === 'd7_14') return r.aging_days > 7  && r.aging_days <= 14
    if (chip === 'gt14')  return r.aging_days > 14
    return true
})
```

Chip 按钮区更新为：

```tsx
<>
    <Chip active={chip==='all'}   onClick={()=>setChip('all')}>全部</Chip>
    <Chip active={chip==='le3'}   onClick={()=>setChip('le3')}  color="blue">≤3天</Chip>
    <Chip active={chip==='d3_7'}  onClick={()=>setChip('d3_7')} color="blue">3-7天</Chip>
    <Chip active={chip==='d7_14'} onClick={()=>setChip('d7_14')} color="red">7-14天</Chip>
    <Chip active={chip==='gt14'}  onClick={()=>setChip('gt14')} color="red">&gt;14天</Chip>
</>
```

**Step 4: 更新 `AlertTable` 组件**

新列顺序，移除偏差和理论余料列：

```tsx
<thead>
    <tr>
        {['工单号','物料编号','物料描述','线边仓','实际库存量','单位','库龄','条码数'].map(h => (
            <th key={h} className="px-4 py-3">{h}</th>
        ))}
    </tr>
</thead>
<tbody>
    {rows.map((r, i) => (
        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
            <td className="px-4 py-3 font-medium text-white">{r.shop_order}</td>
            <td className="px-4 py-3">{r.material_code}</td>
            <td className="px-4 py-3 max-w-xs truncate text-gray-300" title={r.material_desc}>{r.material_desc}</td>
            <td className="px-4 py-3 text-gray-300">{r.warehouse}</td>
            <td className="px-4 py-3 font-medium text-white">{r.actual_inventory?.toFixed(2)}</td>
            <td className="px-4 py-3 text-gray-400">{r.unit || '-'}</td>
            <td className="px-4 py-3"><AgingBadge days={r.aging_days} /></td>
            <td className="px-4 py-3 text-center text-gray-400">{r.barcode_count ?? '-'}</td>
        </tr>
    ))}
</tbody>
```

**Step 5: 支持 URL 参数 `?aging=` 自动筛选（从仪表盘色带跳转）**

在 `DetailPage` 组件顶部加入：

```typescript
import { useEffect, useState } from 'react'

// 在 state 初始化之前读取 URL 参数
const urlParams = new URLSearchParams(window.location.search)
const agingParam = urlParams.get('aging')
const initialChip = (['le3','d3_7','d7_14','gt14'].includes(agingParam || '')
    ? agingParam : 'all') as typeof chip
const [chip, setChip] = useState(initialChip)
```

**Step 6: 验证明细页**

浏览器访问 `http://localhost:5173/detail`：
- 离场审计 Tab 显示 8 列，无偏差列
- 库龄列颜色按天数正确变色（绿→红）
- Chip 筛选 `>14天` 只显示库龄 > 14 天的行
- 从仪表盘色带点击跳转后，明细页自动筛选对应区间

**Step 7: Commit**

```bash
git add frontend/src/pages/DetailPage.tsx
git commit -m "feat(detail): replace deviation with aging column, add aging chip filters"
```

---

## 验收清单

- [ ] `KPIHistory` 表含 `confirmed_alert_count` / `unmatched_current_count` / `legacy_count` 三列
- [ ] `run_and_sync()` 后三列有非零值
- [ ] `/api/kpi/summary` 返回新三字段
- [ ] `/api/kpi/aging-distribution` 返回 6 个键的分布字典
- [ ] `/api/alerts/list` 返回含 `aging_days` 和 `unit`
- [ ] 仪表盘显示 5 张卡片，颜色和备注正确
- [ ] 库龄色带 6 个色块有数值，点击跳转到明细页并自动筛选
- [ ] 明细页离场审计 Tab 显示 8 列，无偏差/理论余料列
- [ ] 明细页库龄列颜色规则正确（≤3天绿，>30天红）
- [ ] Chip 筛选按库龄区间正确过滤
- [ ] `npm run build` 无 TypeScript 错误
