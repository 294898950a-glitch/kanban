# Phase 3 KPI 精修实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 9 处 KPI 去偏差化遗留问题，补齐条码追溯，更新指标说明页。

**Architecture:** 后端加一个 barcode_list 字段 + 修 4 个接口；前端修 3 个页面组件。改动集中、互不依赖，可按顺序执行。

**Tech Stack:** Python + SQLAlchemy + FastAPI / React 18 + TypeScript + Tailwind CSS

---

## Task 1: `models.py` — AlertReportSnapshot 新增 barcode_list 字段

**Files:**
- Modify: `src/db/models.py`

**Step 1: 在 `AlertReportSnapshot` 的 `is_legacy` 字段之后插入**

```python
barcode_list = Column(Text, default="[]")  # JSON 字符串，存条码列表
```

**Step 2: 验证建表（幂等）**

```bash
export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
python3 -c "
from src.db.database import engine, Base
from src.db import models
Base.metadata.create_all(bind=engine)
print('OK')
"
```

Expected: 输出 `OK`，无报错。`alert_report_snapshots` 表新增 `barcode_list` 列（SQLite ALTER TABLE 会自动执行）。

**Step 3: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add barcode_list field to AlertReportSnapshot"
```

---

## Task 2: `build_report.py` — 聚合时收集条码列表

**Files:**
- Modify: `src/analysis/build_report.py`

**Step 1: 读取 build_return_alert() 函数，找到 results.append({...}) 块**

在现有 `results.append({...})` 中新增 `barcode_list` 字段。

先找到聚合逻辑：函数中按 `(wo, mat)` 分组的逻辑，找到 `inv` 变量来源（通常是库存分组后的代表行）。

**Step 2: 收集条码列表**

在 `results.append({...})` 中新增：

```python
# 收集该组的所有条码（库存按 wo+mat 聚合前，需从原始行中收集）
barcodes = list({
    row.get("条码", "") or row.get("barcode", "")
    for row in inv_rows  # inv_rows 是该 (wo, mat) 组合的所有原始库存行
    if row.get("条码") or row.get("barcode")
})
results.append({
    ...（原有字段保持不变）...
    "barcode_list": barcodes,
})
```

注意：需要先确认 `build_return_alert()` 的原始分组变量名称，读取文件后按实际代码修改。

**Step 3: 验证**

```bash
export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
python3 -c "
from src.analysis.build_report import run
alert, issue, quality = run()
sample = [r for r in alert if r.get('barcode_list')][:3]
for r in sample:
    print(r['工单号'], r['物料编号'], r['barcode_list'][:3])
"
```

Expected: 打印出若干行，`barcode_list` 为非空列表。

**Step 4: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat(analysis): collect barcode_list per alert group"
```

---

## Task 3: `sync.py` — 写入 barcode_list

**Files:**
- Modify: `src/db/sync.py`

**Step 1: 在 AlertReportSnapshot 写入逻辑中新增 barcode_list**

找到 `AlertReportSnapshot(...)` 构造处，新增：

```python
import json
# ...
barcode_list=json.dumps(row.get("barcode_list", []), ensure_ascii=False),
```

**Step 2: 验证同步写入**

```bash
python3 src/db/sync.py
python3 -c "
from src.db.database import SessionLocal
from src.db.models import AlertReportSnapshot, KPIHistory
from sqlalchemy import select, desc
import json
db = SessionLocal()
latest = db.execute(select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)).scalar_one()
sample = db.execute(
    select(AlertReportSnapshot)
    .where(AlertReportSnapshot.batch_id == latest.batch_id)
    .limit(3)
).scalars().all()
for r in sample:
    print(r.material_code, json.loads(r.barcode_list or '[]')[:2])
db.close()
"
```

Expected: 打印出物料编号及对应的前 2 个条码。

**Step 3: Commit**

```bash
git add src/db/sync.py
git commit -m "feat(sync): write barcode_list to AlertReportSnapshot"
```

---

## Task 4: `main.py` — 修复四个接口

**Files:**
- Modify: `src/api/main.py`

**Step 1: 修复 `/api/alerts/top10`**

将现有实现替换为：

```python
COMPLETED_STATUSES = {'Completado', '完成', 'Completed', '已完成', 'Se ha iniciado la construcción'}

@app.get("/api/alerts/top10")
def get_alerts_top10():
    """当期退料预警：已完工且仍有库存，按实际库存量排序"""
    db = SessionLocal()
    try:
        latest_kpi = db.execute(
            select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
        ).scalar_one_or_none()
        if not latest_kpi:
            return []

        def _calc_aging(rt) -> float:
            try:
                from datetime import datetime as dt
                s = str(rt).strip().split(" ")[0].replace("/", "-")
                parts = s.split("-")
                s = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                return round((dt.utcnow() - dt.strptime(s, "%Y-%m-%d")).total_seconds() / 86400, 1)
            except Exception:
                return -1.0

        rows = db.execute(
            select(AlertReportSnapshot)
            .where(AlertReportSnapshot.batch_id == latest_kpi.batch_id)
            .where(AlertReportSnapshot.is_legacy == 0)
            .where(AlertReportSnapshot.order_status.in_(COMPLETED_STATUSES))
            .order_by(desc(AlertReportSnapshot.actual_inventory))
            .limit(10)
        ).scalars().all()

        return [
            {
                "shop_order": r.shop_order,
                "material_code": r.material_code,
                "material_desc": r.material_desc,
                "warehouse": r.warehouse,
                "actual_inventory": r.actual_inventory,
                "unit": r.unit,
                "barcode_count": r.barcode_count,
                "aging_days": _calc_aging(r.receive_time),
            }
            for r in rows
        ]
    finally:
        db.close()
```

**Step 2: 修复 `/api/issues/top5`**

将返回字段扩展为：

```python
return [
    {
        "material_code": t.material_code,
        "production_line": t.production_line,
        "related_wo": t.related_wo,
        "demand_qty": t.demand_qty,
        "actual_qty": t.actual_qty,
        "over_issue_qty": t.over_issue_qty,
        "over_issue_rate": t.over_issue_rate,
        "bom_demand_qty": t.bom_demand_qty,
        "over_vs_bom_rate": t.over_vs_bom_rate,
    }
    for t in top5
]
```

**Step 3: 修复 `/api/kpi/trend`**

在返回字典中新增 `confirmed_alert_count`：

```python
return [
    {
        "timestamp": h.timestamp.strftime("%m-%d %H:%M"),
        "alert_group_count": h.alert_group_count,
        "high_risk_count": h.high_risk_count,
        "confirmed_alert_count": h.confirmed_alert_count or 0,
        "over_issue_lines": h.over_issue_lines,
    }
    for h in history
]
```

**Step 4: 修复 `/api/alerts/list`**

在返回字典中新增 `barcode_list`：

```python
import json
# ...
"barcode_list": json.loads(r.barcode_list or "[]"),
```

**Step 5: 验证接口**

```bash
export PYTHONPATH=/home/chenweijie/projects/matetial_monitor
uvicorn src.api.main:app --reload &
sleep 2
curl -s http://localhost:8000/api/alerts/top10 | python3 -m json.tool | head -30
curl -s http://localhost:8000/api/issues/top5 | python3 -m json.tool | head -30
curl -s http://localhost:8000/api/kpi/trend | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d[0].keys()) if d else 'empty')"
```

Expected:
- `top10` 返回含 `aging_days`、`unit`、`barcode_count` 的列表，无 `deviation`
- `top5` 返回含 `over_issue_rate`、`bom_demand_qty`、`over_vs_bom_rate`
- `trend` 返回含 `confirmed_alert_count` 键

**Step 6: Commit**

```bash
git add src/api/main.py
git commit -m "fix(api): remove deviation from top10, enrich top5, add confirmed_alert_count to trend"
```

---

## Task 5: `Dashboard.tsx` — 色带标注、TOP 列表、趋势图

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: 补全色带标注**

找到以下代码：

```tsx
<div className="flex justify-between text-[10px] text-gray-500 mt-1 px-1">
    <span>健康 (≤1天)</span>
    <span>轻度警告 (3-7天)</span>
    <span>严重超期 (&gt;30天)</span>
</div>
```

替换为：

```tsx
<div className="flex justify-between text-[10px] text-gray-500 mt-1">
    <span>健康<br/>≤1天</span>
    <span>观察中<br/>1-3天</span>
    <span>开始关注<br/>3-7天</span>
    <span>需跟进<br/>7-14天</span>
    <span>滞留风险<br/>14-30天</span>
    <span>严重滞留<br/>&gt;30天</span>
</div>
```

**Step 2: 更新 AlertTop interface**

```typescript
interface AlertTop {
    shop_order: string;
    material_code: string;
    material_desc: string;
    warehouse: string;
    actual_inventory: number;
    unit: string;
    barcode_count: number;
    aging_days: number;
}
```

**Step 3: 重写 TOP 离场卡片**

找到 TOP 离场偏差组合的整个 `<div className="glass-panel p-6 flex flex-col max-h-[400px]">` 块，替换为：

```tsx
<div className="glass-panel p-6 flex flex-col max-h-[400px]">
    <h3 className="text-lg font-bold mb-4 flex items-center text-red-400">
        <span className="w-2 h-6 bg-red-500 rounded mr-3"></span>
        退料预警 · 滞留最多 TOP10
    </h3>
    <div className="overflow-y-auto pr-2 flex-grow space-y-2">
        {alerts.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">暂无退料预警</p>
        ) : (
            alerts.map((a, i) => (
                <div key={i} className="bg-gray-800 bg-opacity-50 p-3 rounded border border-gray-700 hover:border-red-500/50 transition-colors">
                    <div className="flex justify-between items-start mb-1">
                        <span className="text-xs font-semibold text-white">{a.shop_order}</span>
                        <AgingBadgeSmall days={a.aging_days} />
                    </div>
                    <div className="text-xs text-gray-400 truncate mb-1" title={a.material_desc}>{a.material_desc}</div>
                    <div className="flex justify-between text-[10px] text-gray-500">
                        <span>{a.warehouse}</span>
                        <span className="text-blue-400 font-medium">{a.actual_inventory?.toFixed(0)} {a.unit}</span>
                    </div>
                </div>
            ))
        )}
    </div>
</div>
```

在文件顶部（组件外）新增 AgingBadgeSmall 组件：

```typescript
function AgingBadgeSmall({ days }: { days: number }) {
    if (days < 0) return <span className="text-gray-500 text-[10px]">-</span>
    const cls =
        days <= 1  ? 'text-green-400' :
        days <= 3  ? 'text-emerald-400' :
        days <= 7  ? 'text-yellow-400' :
        days <= 14 ? 'text-orange-400' :
        days <= 30 ? 'text-orange-300' :
                     'text-red-400 font-bold'
    return <span className={`text-[10px] ${cls}`}>{Math.floor(days)}天</span>
}
```

**Step 4: 更新 IssueTop interface 并重写进场表格**

```typescript
interface IssueTop {
    material_code: string;
    production_line: string;
    related_wo: string;
    demand_qty: number;
    actual_qty: number;
    over_issue_qty: number;
    over_issue_rate: number;
    bom_demand_qty: number;
    over_vs_bom_rate: number;
}
```

找到进场超发预警表格的 `<table>` 块，替换表头和行内容：

```tsx
<thead className="bg-gray-800 text-gray-400">
    <tr>
        <th className="px-3 py-2 text-left rounded-tl">物料编号</th>
        <th className="px-3 py-2 text-left">产线</th>
        <th className="px-3 py-2 text-left">关联工单</th>
        <th className="px-3 py-2 text-right">计划</th>
        <th className="px-3 py-2 text-right">实发</th>
        <th className="px-3 py-2 text-right">超发量</th>
        <th className="px-3 py-2 text-right rounded-tr">超发率%(BOM口径)</th>
    </tr>
</thead>
<tbody>
    {issues.map((issue, idx) => {
        const rateColor = (issue.over_vs_bom_rate ?? 0) > 50
            ? 'text-red-400' : (issue.over_vs_bom_rate ?? 0) > 20
            ? 'text-orange-400' : 'text-yellow-400'
        return (
            <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                <td className="px-3 py-2 font-medium text-white">{issue.material_code}</td>
                <td className="px-3 py-2 text-sm">{issue.production_line || '-'}</td>
                <td className="px-3 py-2 text-sm text-gray-400">{issue.related_wo || '-'}</td>
                <td className="px-3 py-2 text-right text-sm">{issue.demand_qty?.toFixed(0)}</td>
                <td className="px-3 py-2 text-right text-sm">{issue.actual_qty?.toFixed(0)}</td>
                <td className="px-3 py-2 text-right font-bold text-yellow-400">+{issue.over_issue_qty?.toFixed(0)}</td>
                <td className={`px-3 py-2 text-right font-bold ${rateColor}`}>
                    {issue.over_vs_bom_rate != null ? `${issue.over_vs_bom_rate.toFixed(1)}%` : '-'}
                </td>
            </tr>
        )
    })}
</tbody>
```

**Step 5: 更新 KPITrend interface 和趋势图**

```typescript
interface KPITrend {
    timestamp: string;
    alert_group_count: number;
    high_risk_count: number;
    confirmed_alert_count: number;
    over_issue_lines: number;
}
```

在 `renderTrendChart` 中，将 `高风险组数` 系列改为 `当期退料预警`：

```typescript
// 旧
{ name: '高风险组数', ..., data: trendData.map(d => d.high_risk_count), ... }

// 新
{ name: '当期退料预警', ..., data: trendData.map(d => d.confirmed_alert_count), ... }
```

同时更新 legend：
```typescript
legend: { data: ['退料预警总量', '当期退料预警', '超发预警行数'], ... }
```

**Step 6: 验证**

```bash
cd /home/chenweijie/projects/matetial_monitor/frontend && npm run dev
```

浏览器访问 `http://localhost:5173`：
- 色带下方有 6 条标注，文字清晰可读
- TOP 离场标题为"退料预警 · 滞留最多 TOP10"，每行显示库龄天数（无偏差）
- TOP 进场表格有 7 列，含超发率%(BOM口径)
- 趋势图图例显示"当期退料预警"（非高风险组数）

**Step 7: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "fix(dashboard): fix aging labels, redesign top10/top5, align trend to confirmed_alert_count"
```

---

## Task 6: `DetailPage.tsx` — AlertTable 新增条码列

**Files:**
- Modify: `frontend/src/pages/DetailPage.tsx`

**Step 1: 更新 AlertRow interface**

```typescript
interface AlertRow {
    shop_order: string; material_code: string; material_desc: string
    warehouse: string; actual_inventory: number; barcode_count: number;
    unit: string; aging_days: number;
    barcode_list: string[];  // 新增
}
```

**Step 2: 新增 BarcodeCell 组件**

```typescript
function BarcodeCell({ list, count }: { list: string[]; count: number }) {
    if (!list || list.length === 0) return <span className="text-gray-600 text-xs">{count}个</span>
    const display = list.slice(0, 3)
    const rest = list.length - 3
    return (
        <div className="text-xs text-gray-400 space-y-0.5">
            {display.map((bc, i) => (
                <div key={i} className="font-mono text-[10px] bg-gray-800 px-1.5 py-0.5 rounded">{bc}</div>
            ))}
            {rest > 0 && (
                <span className="text-gray-500 cursor-help" title={list.slice(3).join('\n')}>
                    +{rest} 更多
                </span>
            )}
        </div>
    )
}
```

**Step 3: 更新 AlertTable 表头和行**

将表头从 `['工单号', '物料编号', '物料描述', '线边仓', '实际库存', '单位', '条码数', '库龄分析']`

改为 `['工单号', '物料编号', '物料描述', '线边仓', '实际库存', '单位', '库龄分析', '条码']`

（移除「条码数」单独列，条码数量在 BarcodeCell 中作为 fallback 显示）

对应 `<td>` 更新（替换最后两列）：

```tsx
<td className="px-4 py-3"><AgingBadge days={r.aging_days} /></td>
<td className="px-4 py-3 min-w-[120px]"><BarcodeCell list={r.barcode_list ?? []} count={r.barcode_count} /></td>
```

**Step 4: 验证**

浏览器访问 `http://localhost:5173/detail`：
- 离场审计 Tab 末列显示条码字符串（最多 3 条 + "+N 更多"）
- hover "+N 更多" 时 tooltip 显示完整条码列表

**Step 5: Commit**

```bash
git add frontend/src/pages/DetailPage.tsx
git commit -m "feat(detail): show barcode_list in alert table with expandable display"
```

---

## Task 7: `MetricsDoc.tsx` — 离场审计节重写

**Files:**
- Modify: `frontend/src/pages/MetricsDoc.tsx`

**Step 1: 将离场审计 section 整体替换**

找到：
```tsx
<section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
    <h2 className="text-lg font-semibold text-blue-400 mb-1">离场审计 · 退料预警</h2>
    ...（到 </section>）
```

替换为：

```tsx
<section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
    <h2 className="text-lg font-semibold text-blue-400 mb-1">离场审计 · 退料预警</h2>
    <p className="text-gray-400 text-sm mb-4">
        工单完工后，线边仓仍有该工单对应物料的库存，说明存在未退料风险。
        系统<strong className="text-white">不依赖理论余料或偏差计算</strong>——
        偏差会受提前合并送料、返工超耗、BOM 滞后等因素干扰，无法作为现场操作依据。
    </p>

    <h3 className="text-sm font-medium text-gray-300 mb-2">触发条件</h3>
    <FormulaBox>2026 年工单  ×  已完工  ×  线边仓仍有库存  →  退料预警</FormulaBox>

    <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-300 mb-2">KPI 卡片说明</h3>
        <MetricTable rows={[
            ['当期退料预警', '分析计算', '匹配 2026 年工单 + 已完工 + 线边仓仍有库存，需立即退料处理'],
            ['工单范围外库存', '分析计算', '接收时间≥2026 但关联工单不在 IMES 监控窗口，需人工核查归属'],
            ['历史遗留库存', '分析计算', '接收时间<2026 或无记录，保留展示但不计入预警'],
            ['当期平均库龄', '分析计算', '仅统计当期退料预警物料的平均滞留时长（小时）'],
        ]} />
    </div>

    <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-300 mb-2">库龄分布色带</h3>
        <div className="flex gap-1 text-[10px] text-center">
            {[
                { label: '≤1天\n健康', bg: 'bg-green-700' },
                { label: '1-3天\n观察中', bg: 'bg-lime-700' },
                { label: '3-7天\n开始关注', bg: 'bg-yellow-700' },
                { label: '7-14天\n需跟进', bg: 'bg-orange-700' },
                { label: '14-30天\n滞留风险', bg: 'bg-orange-900' },
                { label: '>30天\n严重滞留', bg: 'bg-red-800' },
            ].map(({ label, bg }) => (
                <div key={label} className={`flex-1 ${bg} rounded py-1.5 text-white whitespace-pre-line leading-tight`}>{label}</div>
            ))}
        </div>
    </div>

    <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-300 mb-2">字段说明</h3>
        <MetricTable rows={[
            ['实际库存量', 'SSRS 线边仓', '该（工单, 物料）组合在线边仓的现存总量（所有条码汇总）'],
            ['单位', 'SSRS 线边仓', '物料计量单位（EA / PCS 等）'],
            ['条码', 'SSRS 线边仓', '该组合在线边仓的独立批次/条码列表，可追溯实物位置'],
            ['库龄', '分析计算', '当前时间 − 最早接收时间（天），颜色规则与色带一致'],
        ]} />
    </div>
</section>
```

**Step 2: 验证**

浏览器访问 `http://localhost:5173/docs`：
- 离场审计节显示新触发条件公式（无偏差字段）
- KPI 卡片说明表有 4 行
- 库龄色带有 6 个色块
- 字段说明表有 4 行（实际库存/单位/条码/库龄）

**Step 3: Commit**

```bash
git add frontend/src/pages/MetricsDoc.tsx
git commit -m "fix(docs): rewrite departure audit section to remove deviation, add KPI cards and aging guide"
```

---

## Task 8: 前端构建验证

**Step 1: TypeScript 全量构建**

```bash
cd /home/chenweijie/projects/matetial_monitor/frontend && npm run build
```

Expected: 无 TypeScript 错误，`dist/` 目录生成。

**Step 2: 若有类型错误**

常见问题：
- `IssueTop` 新增字段在模板中未判空 → 加 `?? '-'` 或 `?? 0`
- `barcode_list` 在旧批次数据中为 `null` → `r.barcode_list ?? []`

---

## 验收清单

- [ ] 色带下方有 6 条标注（健康/观察中/开始关注/需跟进/滞留风险/严重滞留）
- [ ] TOP 离场标题"退料预警 · 滞留最多 TOP10"，无偏差值
- [ ] TOP 离场每行显示库龄天数（颜色）
- [ ] TOP 进场表格 7 列，含超发率%(BOM口径)
- [ ] 趋势图图例显示"当期退料预警"（非高风险组数）
- [ ] 数据明细离场 Tab 末列显示条码列表
- [ ] 指标说明页无偏差/理论余料公式
- [ ] 指标说明页含 KPI 卡片说明表 + 库龄色带
- [ ] `npm run build` 无 TypeScript 错误
