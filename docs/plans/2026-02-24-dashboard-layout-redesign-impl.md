# Dashboard Layout Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `plan_issue_date` field to the issue audit pipeline, add `avg_aging_hours` to trend API, and redesign Dashboard layout (Row 1: 50/50 trend charts; Row 2: 1/3 alerts + 2/3 issues table with new column).

**Architecture:** Backend-first (data pipeline → DB → API), then frontend. Each task is independently testable. No test framework in this project — verification is via `curl` / Python repl / browser.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy · SQLite · React 18 + TypeScript · ECharts · Tailwind CSS · pnpm

---

## Task 1: Inject `_ppStartTime` in nwms_scraper.py

**Files:**
- Modify: `src/scrapers/nwms_scraper.py:266`

**Step 1: Add ppStartTime extraction alongside other head fields**

At line 266 (`doc_status = head.get("instructionDocStatus", "")`), add one line immediately after:

```python
        doc_id = str(head.get("instructionDocId", ""))
        doc_num = head.get("demandListNumber", "")
        wo_num = head.get("workOrderNum", "")
        line = head.get("productionLine", "")
        warehouse = head.get("wareHouse", "")
        doc_status = head.get("instructionDocStatus", "")
        pp_start_time = head.get("ppStartTime", "")   # ← ADD THIS LINE
```

**Step 2: Inject into each line dict**

At line 288 (`ln["_docStatus"] = doc_status`), add one line immediately after:

```python
                ln["_instructionDocId"] = doc_id
                ln["_demandListNumber"] = doc_num
                ln["_workOrderNum"] = wo_num
                ln["_productionLine"] = line
                ln["_wareHouse"] = warehouse
                ln["_docStatus"] = doc_status
                ln["_ppStartTime"] = pp_start_time   # ← ADD THIS LINE
```

**Step 3: Verify (quick check — no full scrape needed)**

```python
# In Python REPL
import json
from pathlib import Path
data = json.loads(Path("data/raw/nwms_issue_details_latest.json").read_text())
print(data[0].keys())          # should include _ppStartTime (may be "" if field absent in API)
print(data[0].get("_ppStartTime", "KEY_MISSING"))
```

> **Note:** The field `ppStartTime` may not be in the current snapshot file yet. The field will populate on the next scrape run. Proceed to Task 2.

**Step 4: Commit**

```bash
git add src/scrapers/nwms_scraper.py
git commit -m "feat: inject _ppStartTime from NWMS head table into issue line records"
```

---

## Task 2: Write `计划发料日期` to issue_audit_report.csv

**Files:**
- Modify: `src/analysis/build_report.py:278-300`

**Step 1: Add field to the results dict**

In `build_issue_audit()`, find the `results.append({...})` block (around line 278). Add `"计划发料日期"` as the **last key** (after `"IMES工单状态"`):

```python
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
                "计划发料日期": ln.get("_ppStartTime", ""),   # ← ADD THIS LINE
            })
```

**Step 2: Verify field appears in CSV**

```bash
PYTHONPATH=. python3 src/analysis/build_report.py
head -1 data/raw/issue_audit_report.csv | tr ',' '\n' | grep -n "计划"
# Expected: shows "计划发料日期" column
```

**Step 3: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat: add 计划发料日期 field from ppStartTime to issue audit report"
```

---

## Task 3: Add `plan_issue_date` column to DB model

**Files:**
- Modify: `src/db/models.py:76` (after `over_vs_bom_rate`)

**Step 1: Add column to IssueAuditSnapshot**

Insert after line 75 (`over_vs_bom_rate = Column(Float, default=0.0)`):

```python
    over_vs_bom_rate = Column(Float, default=0.0)           # 超发率%(vs BOM)
    plan_issue_date  = Column(String(50), default="")        # 计划发料日期(ppStartTime)  ← ADD
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat: add plan_issue_date column to IssueAuditSnapshot model"
```

---

## Task 4: Migrate existing DB (idempotent ALTER TABLE)

**Files:**
- Modify: `tools/migrate_db.py:93` (before `conn.close()`)

**Step 1: Add Step 6 migration block**

Replace the `conn.close()` line with:

```python
# 6. 给 issue_audit_snapshots 表加 plan_issue_date 列
try:
    cursor.execute("ALTER TABLE issue_audit_snapshots ADD COLUMN plan_issue_date VARCHAR(50) DEFAULT '';")
    conn.commit()
    print("[MIGRATE] ✅ issue_audit_snapshots.plan_issue_date 列新增成功")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("[MIGRATE] ℹ️  issue_audit_snapshots.plan_issue_date 列已存在，跳过")
    else:
        print(f"[MIGRATE] ❌ 错误: {e}")

conn.close()
print("[MIGRATE] 迁移完成")
```

**Step 2: Run migration**

```bash
PYTHONPATH=. python3 tools/migrate_db.py
# Expected: "✅ issue_audit_snapshots.plan_issue_date 列新增成功" OR "ℹ️  已存在，跳过"
```

**Step 3: Verify column exists**

```bash
sqlite3 data/matetial_monitor.db ".schema issue_audit_snapshots" | grep plan_issue_date
# Expected: plan_issue_date VARCHAR(50)
```

**Step 4: Commit**

```bash
git add tools/migrate_db.py
git commit -m "feat: migrate DB to add plan_issue_date column to issue_audit_snapshots"
```

---

## Task 5: Write `plan_issue_date` in sync.py

**Files:**
- Modify: `src/db/sync.py:89-107` (IssueAuditSnapshot insert block)

**Step 1: Add field to IssueAuditSnapshot constructor call**

Find the `IssueAuditSnapshot(...)` call (line ~89). Add after `over_vs_bom_rate=...`:

```python
            issue_inserts.append(IssueAuditSnapshot(
                batch_id=batch_id,
                timestamp=ts,
                instruction_doc_id=safe_str(r.get("备料单ID")),
                demand_list_number=safe_str(r.get("备料单号")),
                doc_status=safe_str(r.get("备料单状态")),
                related_wo=safe_str(r.get("关联工单")),
                material_code=safe_str(r.get("物料编号")),
                demand_qty=safe_float(r.get("计划发料量(demandQty)")),
                actual_qty=safe_float(r.get("实际发料量(actualQty)")),
                over_issue_qty=safe_float(r.get("超发量")),
                over_issue_rate=safe_float(r.get("超发率(%)")),
                is_over_issue=safe_str(r.get("是否超发")),
                production_line=safe_str(r.get("产线")),
                warehouse=safe_str(r.get("仓库")),
                bom_demand_qty=safe_float(r.get("BOM标准需求量(sumQty)")),
                over_vs_bom_qty=safe_float(r.get("超发量(vs BOM)")),
                over_vs_bom_rate=safe_float(r.get("超发率%(vs BOM)")),
                plan_issue_date=safe_str(r.get("计划发料日期")),   # ← ADD THIS LINE
            ))
```

**Step 2: Verify by running a fresh sync**

```bash
PYTHONPATH=. python3 -c "from src.db.sync import run_and_sync; run_and_sync()"
# Then verify:
sqlite3 data/matetial_monitor.db "SELECT plan_issue_date FROM issue_audit_snapshots LIMIT 5;"
# Values will be "" until nwms_scraper is re-run with ppStartTime populated
```

**Step 3: Commit**

```bash
git add src/db/sync.py
git commit -m "feat: persist plan_issue_date in IssueAuditSnapshot sync"
```

---

## Task 6: Expose `plan_issue_date` in API + add `avg_aging_hours` to trend

**Files:**
- Modify: `src/api/main.py`

**Step 1: Add `avg_aging_hours` to `/api/kpi/trend` response**

Find the `return [...]` block in `get_kpi_trend()` (line ~73). Add `avg_aging_hours`:

```python
        return [
            {
                "timestamp": h.timestamp.strftime("%m-%d %H:%M"),
                "alert_group_count": h.alert_group_count,
                "high_risk_count": h.high_risk_count,
                "confirmed_alert_count": h.confirmed_alert_count or 0,
                "over_issue_lines": h.over_issue_lines,
                "avg_aging_hours": h.avg_aging_hours or 0.0,   # ← ADD THIS LINE
            }
            for h in history
        ]
```

**Step 2: Add `plan_issue_date` to `/api/issues/top5` response**

Find the `return [...]` in `get_issues_top5()` (line ~196). Add field:

```python
        return [
            {
                "material_code": t.material_code,
                "production_line": t.production_line,
                "related_wo": t.related_wo,
                "plan_issue_date": t.plan_issue_date or "",   # ← ADD THIS LINE
                "demand_qty": t.demand_qty,
                "actual_qty": t.actual_qty,
                "over_issue_qty": t.over_issue_qty,
                "over_issue_rate": t.over_issue_rate,
                "bom_demand_qty": t.bom_demand_qty,
                "over_vs_bom_rate": t.over_vs_bom_rate,
            }
            for t in rows
        ]
```

**Step 3: Add `plan_issue_date` to `/api/issues/list` response**

Find the `return [...]` in `get_issues_list()` (line ~302). Add field:

```python
        return [
            {
                "demand_list_number": r.demand_list_number,
                "material_code": r.material_code,
                "related_wo": r.related_wo,
                "production_line": r.production_line,
                "plan_issue_date": r.plan_issue_date or "",   # ← ADD THIS LINE
                "demand_qty": r.demand_qty,
                "actual_qty": r.actual_qty,
                "over_issue_qty": r.over_issue_qty,
            }
            for r in rows
        ]
```

**Step 4: Restart backend and verify**

```bash
pkill -f "uvicorn src.api.main" 2>/dev/null; sleep 1
PYTHONPATH=. venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/api/kpi/trend | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d[0].keys()))"
# Expected: includes 'avg_aging_hours'
curl -s "http://localhost:8000/api/issues/top5" | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d[0].keys()) if d else 'empty')"
# Expected: includes 'plan_issue_date'
```

**Step 5: Commit**

```bash
git add src/api/main.py
git commit -m "feat: add avg_aging_hours to trend API and plan_issue_date to issues APIs"
```

---

## Task 7: Dashboard.tsx — Layout Rewrite

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

This task has the most changes. Apply them in sub-steps.

### Step 7a: Update TypeScript interfaces

**Add `avg_aging_hours` to `KPITrend` interface** (line 27-33):

```typescript
interface KPITrend {
    timestamp: string;
    alert_group_count: number;
    high_risk_count: number;
    confirmed_alert_count: number;
    over_issue_lines: number;
    avg_aging_hours: number;   // ← ADD
}
```

**Add `plan_issue_date` to `IssueTop` interface** (line 45-55):

```typescript
interface IssueTop {
    material_code: string;
    production_line: string;
    related_wo: string;
    plan_issue_date: string;   // ← ADD
    demand_qty: number;
    actual_qty: number;
    over_issue_qty: number;
    over_issue_rate: number;
    bom_demand_qty: number;
    over_vs_bom_rate: number;
}
```

### Step 7b: Add agingChartRef

Add `agingChartRef` alongside `trendChartRef` (line 84):

```typescript
    const trendChartRef = useRef<HTMLDivElement>(null)
    const agingChartRef = useRef<HTMLDivElement>(null)   // ← ADD
```

### Step 7c: Add renderAgingChart function

Add this function immediately after `renderTrendChart` closes (after line 169), before the `useEffect`:

```typescript
    const renderAgingChart = (trendData: KPITrend[]) => {
        if (!agingChartRef.current) return
        const chart = echarts.getInstanceByDom(agingChartRef.current) || echarts.init(agingChartRef.current)

        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>平均库龄: ${p[0].value} h` },
            legend: { data: ['当期平均库龄'], textStyle: { color: '#fff' } },
            grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: trendData.map(d => d.timestamp),
                axisLabel: { color: '#ccc' }
            },
            yAxis: {
                type: 'value',
                name: '小时',
                nameTextStyle: { color: '#ccc' },
                axisLabel: { color: '#ccc' },
                splitLine: { lineStyle: { color: '#333' } }
            },
            series: [
                {
                    name: '当期平均库龄',
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.1 },
                    data: trendData.map(d => d.avg_aging_hours),
                    itemStyle: { color: '#a855f7' },
                    lineStyle: { color: '#a855f7' }
                }
            ]
        })
    }
```

### Step 7d: Update fetchData to call renderAgingChart

Change `renderTrendChart(trendRes.data)` (line 104) to also call `renderAgingChart`:

```typescript
            renderTrendChart(trendRes.data)
            renderAgingChart(trendRes.data)   // ← ADD
```

### Step 7e: Update useEffect resize handler

Add `agingChartRef` resize alongside `trendChartRef` (line 178-180):

```typescript
        const handleResize = () => {
            if (trendChartRef.current) echarts.getInstanceByDom(trendChartRef.current)?.resize()
            if (agingChartRef.current) echarts.getInstanceByDom(agingChartRef.current)?.resize()   // ← ADD
        }
```

### Step 7f: Rewrite the main layout grid (lines 291-377)

Replace the entire `{/* 中心图表区与明细列表 */}` block (from line 290 `{/* 中心图表区 */}` to line 377 `</div>` that closes the grid) with:

```tsx
            {/* Row 1: 趋势图 50/50 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

                {/* 左：风险趋势折线图 */}
                <div className="glass-panel p-6">
                    <h3 className="text-lg font-bold mb-4 flex items-center">
                        <span className="w-2 h-6 bg-blue-500 rounded mr-3"></span>
                        风险项时间趋势分析
                    </h3>
                    <div ref={trendChartRef} className="w-full h-80"></div>
                </div>

                {/* 右：库龄趋势折线图 */}
                <div className="glass-panel p-6">
                    <h3 className="text-lg font-bold mb-4 flex items-center">
                        <span className="w-2 h-6 bg-purple-500 rounded mr-3"></span>
                        当期平均库龄趋势
                    </h3>
                    <div ref={agingChartRef} className="w-full h-80"></div>
                </div>
            </div>

            {/* Row 2: 退料预警(1/3) + 超发预警(2/3) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* 左1/3：退料预警全量 */}
                <div className="glass-panel p-6 flex flex-col max-h-[480px]">
                    <h3 className="text-lg font-bold mb-4 flex items-center text-red-400">
                        <span className="w-2 h-6 bg-red-500 rounded mr-3"></span>
                        退料预警 · 按库存量排序（全量）
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

                {/* 右2/3：超发预警全量，含计划发料日期 */}
                <div className="glass-panel p-6 lg:col-span-2">
                    <h3 className="text-lg font-bold mb-4 flex items-center text-yellow-500">
                        <span className="w-2 h-6 bg-yellow-500 rounded mr-3"></span>
                        进场超发预警（全量）
                    </h3>
                    <div className="overflow-x-auto overflow-y-auto max-h-[420px]">
                        <table className="w-full text-left text-sm text-gray-300">
                            <thead className="bg-gray-800 text-gray-400 sticky top-0">
                                <tr>
                                    <th className="px-3 py-2 text-left rounded-tl">物料编号</th>
                                    <th className="px-3 py-2 text-left">产线</th>
                                    <th className="px-3 py-2 text-left">关联工单</th>
                                    <th className="px-3 py-2 text-left">计划发料日期</th>
                                    <th className="px-3 py-2 text-right">计划</th>
                                    <th className="px-3 py-2 text-right">实发</th>
                                    <th className="px-3 py-2 text-right">超发量</th>
                                    <th className="px-3 py-2 text-right rounded-tr">超发率%(BOM口径)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {issues.length === 0 ? (
                                    <tr>
                                        <td colSpan={8} className="px-4 py-8 text-center text-gray-500">暂无超发发料数据</td>
                                    </tr>
                                ) : (
                                    issues.map((issue, idx) => {
                                        const rateColor = (issue.over_vs_bom_rate ?? 0) > 50
                                            ? 'text-red-400' : (issue.over_vs_bom_rate ?? 0) > 20
                                                ? 'text-orange-400' : 'text-yellow-400'
                                        return (
                                            <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                                                <td className="px-3 py-2 font-medium text-white">{issue.material_code}</td>
                                                <td className="px-3 py-2 text-sm">{issue.production_line || '-'}</td>
                                                <td className="px-3 py-2 text-sm text-gray-400">{issue.related_wo || '-'}</td>
                                                <td className="px-3 py-2 text-sm text-gray-400">{issue.plan_issue_date || '-'}</td>
                                                <td className="px-3 py-2 text-right text-sm">{issue.demand_qty?.toFixed(0)}</td>
                                                <td className="px-3 py-2 text-right text-sm">{issue.actual_qty?.toFixed(0)}</td>
                                                <td className="px-3 py-2 text-right font-bold text-yellow-400">+{issue.over_issue_qty?.toFixed(0)}</td>
                                                <td className={`px-3 py-2 text-right font-bold ${rateColor}`}>
                                                    {issue.over_vs_bom_rate != null ? `${issue.over_vs_bom_rate.toFixed(1)}%` : '-'}
                                                </td>
                                            </tr>
                                        )
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
```

### Step 7g: Verify in browser

```bash
cd frontend && pnpm run dev
# Open http://localhost:5173
# Check:
# ✓ Row 1: two equal-width charts side by side
# ✓ Right chart has purple line (may be flat/empty until data populates)
# ✓ Row 2: narrow card list on left, wide table on right
# ✓ 超发 table has 8 columns including "计划发料日期"
# ✓ No TypeScript compile errors in terminal
```

### Step 7h: Commit

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: redesign dashboard layout — 50/50 trend charts, 1/3+2/3 detail row, add aging trend chart and plan_issue_date column"
```

---

## Post-Implementation: Populate Real Data

After all 7 tasks are committed and the backend is restarted:

**Run fresh NWMS scrape to get ppStartTime:**

```bash
PYTHONPATH=. python3 src/scrapers/nwms_scraper.py --start 2026-01-01
PYTHONPATH=. python3 -c "from src.db.sync import run_and_sync; run_and_sync()"
```

**Verify plan_issue_date populated:**

```bash
sqlite3 data/matetial_monitor.db \
  "SELECT material_code, plan_issue_date FROM issue_audit_snapshots WHERE plan_issue_date != '' LIMIT 5;"
```

**Verify aging trend chart renders data:**

```bash
curl -s http://localhost:8000/api/kpi/trend | python3 -c \
  "import json,sys; d=json.load(sys.stdin); [print(x['timestamp'], x['avg_aging_hours']) for x in d[-3:]]"
```

---

## Change Summary

| Task | File | Change |
|------|------|--------|
| 1 | `src/scrapers/nwms_scraper.py` | Extract + inject `_ppStartTime` from head |
| 2 | `src/analysis/build_report.py` | Write `计划发料日期` to issue row |
| 3 | `src/db/models.py` | Add `plan_issue_date` column to IssueAuditSnapshot |
| 4 | `tools/migrate_db.py` | Idempotent ALTER TABLE |
| 5 | `src/db/sync.py` | Persist `plan_issue_date` on insert |
| 6 | `src/api/main.py` | Return `plan_issue_date` in issues APIs + `avg_aging_hours` in trend |
| 7 | `frontend/src/pages/Dashboard.tsx` | Full layout rewrite + aging chart + new table column |
