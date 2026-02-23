# New Pages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 React + FastAPI 仪表盘中新增「指标说明页」和「带筛选器的数据明细页」，并引入 React Router + MD 风格侧边导航栏。

**Architecture:** `App.tsx` 改为路由壳（NavRail + `<Outlet />`），原仪表盘逻辑迁移至 `Dashboard.tsx`，新增两个页面组件；后端新增 3 个列表接口供明细页调用。

**Tech Stack:** React 18 + Vite + TypeScript + Tailwind CSS + react-router-dom v6 + FastAPI + SQLAlchemy

---

## Task 1: 安装 react-router-dom

**Files:**
- Modify: `frontend/package.json`（由 npm 自动更新）

**Step 1: 安装依赖**

```bash
cd frontend && npm install react-router-dom
```

Expected: `added N packages` 无报错。

**Step 2: 验证类型声明已包含**

```bash
ls frontend/node_modules/react-router-dom/dist/index.d.ts
```

Expected: 文件存在（react-router-dom v6 已内置类型，无需单独安装 `@types`）。

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: install react-router-dom"
```

---

## Task 2: 创建 NavRail 导航栏组件

**Files:**
- Create: `frontend/src/components/NavRail.tsx`

**Step 1: 创建文件**

```tsx
// frontend/src/components/NavRail.tsx
import { NavLink } from 'react-router-dom'

const navItems = [
    {
        to: '/',
        label: '仪表盘',
        icon: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 5a1 1 0 011-1h4a1 1 0 011 1v5a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v2a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10-3a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1v-7z" />
            </svg>
        ),
    },
    {
        to: '/docs',
        label: '指标说明',
        icon: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
        ),
    },
    {
        to: '/detail',
        label: '数据明细',
        icon: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 10h18M3 14h18M3 6h18M3 18h18" />
            </svg>
        ),
    },
]

export default function NavRail() {
    return (
        <nav className="fixed left-0 top-0 h-full w-60 bg-gray-900 border-r border-gray-800 flex flex-col z-10">
            {/* Logo 区 */}
            <div className="px-6 py-5 border-b border-gray-800">
                <h1 className="text-sm font-bold text-white leading-tight">物料流转</h1>
                <p className="text-xs text-gray-500 mt-0.5">双向审计监控</p>
            </div>

            {/* 导航项 */}
            <div className="flex-1 px-3 py-4 space-y-1">
                {navItems.map(({ to, label, icon }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === '/'}
                        className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                                isActive
                                    ? 'bg-blue-600 text-white'
                                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                            }`
                        }
                    >
                        {icon}
                        {label}
                    </NavLink>
                ))}
            </div>
        </nav>
    )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/NavRail.tsx
git commit -m "feat: add NavRail navigation component"
```

---

## Task 3: 迁移仪表盘 + 改造 App.tsx 为路由壳

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`（全部替换）

**Step 1: 创建 `frontend/src/pages/` 目录并将 App.tsx 当前主体内容复制为 Dashboard.tsx**

`Dashboard.tsx` = 当前 `App.tsx` 的完整内容，仅修改最后一行 export：

```tsx
// frontend/src/pages/Dashboard.tsx
// 将 App.tsx 全部内容粘贴于此
// 将最后一行改为：
export default function Dashboard() { ... }
// （函数名 App → Dashboard）
```

**Step 2: 将 App.tsx 替换为路由壳**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import NavRail from './components/NavRail'
import Dashboard from './pages/Dashboard'
import MetricsDoc from './pages/MetricsDoc'
import DetailPage from './pages/DetailPage'

export default function App() {
    return (
        <BrowserRouter>
            <div className="flex min-h-screen bg-gray-950 text-white">
                <NavRail />
                <main className="ml-60 flex-1 p-6 overflow-auto">
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/docs" element={<MetricsDoc />} />
                        <Route path="/detail" element={<DetailPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </main>
            </div>
        </BrowserRouter>
    )
}
```

> ⚠️ 此时 MetricsDoc 和 DetailPage 尚未创建，会报 TS 编译错误。下一步先建空占位文件。

**Step 3: 创建两个空占位文件以消除编译错误**

```tsx
// frontend/src/pages/MetricsDoc.tsx
export default function MetricsDoc() {
    return <div className="p-6 text-white">指标说明（开发中）</div>
}
```

```tsx
// frontend/src/pages/DetailPage.tsx
export default function DetailPage() {
    return <div className="p-6 text-white">数据明细（开发中）</div>
}
```

**Step 4: 启动开发服务验证**

```bash
cd frontend && npm run dev
```

Expected: 浏览器打开 `http://localhost:5173`，左侧出现导航栏，`/` 显示原仪表盘内容，`/docs` 和 `/detail` 显示占位文字。

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/
git commit -m "feat: add router shell and extract Dashboard page"
```

---

## Task 4: 后端新增 3 个接口

**Files:**
- Modify: `src/api/main.py`（在文件末尾追加）

**Step 1: 追加 `/api/batches` 接口**

```python
@app.get("/api/batches")
def get_batches():
    """返回所有历史批次列表（降序）"""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(KPIHistory.batch_id, KPIHistory.timestamp)
            .order_by(desc(KPIHistory.timestamp))
        ).all()
        return [{"batch_id": r.batch_id, "timestamp": r.timestamp.isoformat()} for r in rows]
    finally:
        db.close()
```

**Step 2: 追加 `/api/alerts/list` 接口**

```python
@app.get("/api/alerts/list")
def get_alerts_list(batch_id: str = "", q: str = ""):
    """离场审计完整明细，支持关键字过滤（工单号或物料编号）"""
    db = SessionLocal()
    try:
        # 未指定批次时取最新批次
        if not batch_id:
            latest = db.execute(
                select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
            ).scalar_one_or_none()
            if not latest:
                return []
            batch_id = latest.batch_id

        stmt = select(AlertReportSnapshot).where(AlertReportSnapshot.batch_id == batch_id)
        if q:
            stmt = stmt.where(
                AlertReportSnapshot.shop_order.contains(q) |
                AlertReportSnapshot.material_code.contains(q)
            )
        stmt = stmt.order_by(desc(AlertReportSnapshot.deviation))
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "shop_order": r.shop_order,
                "material_code": r.material_code,
                "material_desc": r.material_desc,
                "warehouse": r.warehouse,
                "actual_inventory": r.actual_inventory,
                "theory_remain": r.theory_remain,
                "deviation": r.deviation,
            }
            for r in rows
        ]
    finally:
        db.close()
```

**Step 3: 追加 `/api/issues/list` 接口**

```python
@app.get("/api/issues/list")
def get_issues_list(batch_id: str = "", q: str = ""):
    """进场审计完整明细，支持关键字过滤（物料编号或备料单号）"""
    db = SessionLocal()
    try:
        if not batch_id:
            latest = db.execute(
                select(KPIHistory).order_by(desc(KPIHistory.timestamp)).limit(1)
            ).scalar_one_or_none()
            if not latest:
                return []
            batch_id = latest.batch_id

        stmt = select(IssueAuditSnapshot).where(IssueAuditSnapshot.batch_id == batch_id)
        if q:
            stmt = stmt.where(
                IssueAuditSnapshot.material_code.contains(q) |
                IssueAuditSnapshot.demand_list_number.contains(q)
            )
        stmt = stmt.order_by(desc(IssueAuditSnapshot.over_issue_qty))
        rows = db.execute(stmt).scalars().all()

        return [
            {
                "demand_list_number": r.demand_list_number,
                "material_code": r.material_code,
                "related_wo": r.related_wo,
                "production_line": r.production_line,
                "demand_qty": r.demand_qty,
                "actual_qty": r.actual_qty,
                "over_issue_qty": r.over_issue_qty,
            }
            for r in rows
        ]
    finally:
        db.close()
```

**Step 4: 手动验证接口**

启动后端：
```bash
uvicorn src.api.main:app --reload
```

访问：
- `http://localhost:8000/api/batches` → 应返回批次列表数组
- `http://localhost:8000/api/alerts/list` → 应返回最新批次明细
- `http://localhost:8000/api/alerts/list?q=WO-001` → 应返回工单号含 WO-001 的记录

**Step 5: Commit**

```bash
git add src/api/main.py
git commit -m "feat: add batches/alerts/issues list API endpoints"
```

---

## Task 5: 实现指标说明页

**Files:**
- Modify: `frontend/src/pages/MetricsDoc.tsx`（替换占位内容）

**Step 1: 编写静态内容**

```tsx
// frontend/src/pages/MetricsDoc.tsx

function FormulaBox({ children }: { children: string }) {
    return (
        <code className="block bg-gray-800 text-green-400 font-mono text-sm px-4 py-3 rounded-lg mt-2">
            {children}
        </code>
    )
}

function MetricTable({ rows }: { rows: [string, string, string][] }) {
    return (
        <table className="w-full text-sm mt-3">
            <thead>
                <tr className="text-gray-400 border-b border-gray-700">
                    <th className="text-left py-2 pr-4 font-medium w-1/4">指标</th>
                    <th className="text-left py-2 pr-4 font-medium w-1/4">来源</th>
                    <th className="text-left py-2 font-medium">说明</th>
                </tr>
            </thead>
            <tbody>
                {rows.map(([metric, source, desc]) => (
                    <tr key={metric} className="border-b border-gray-800 text-gray-300">
                        <td className="py-2 pr-4 font-medium text-white">{metric}</td>
                        <td className="py-2 pr-4 text-blue-400 text-xs">{source}</td>
                        <td className="py-2">{desc}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    )
}

export default function MetricsDoc() {
    return (
        <div className="max-w-3xl space-y-8">
            <header>
                <h1 className="text-2xl font-bold text-white">指标说明</h1>
                <p className="text-gray-400 text-sm mt-1">各项监控指标的计算逻辑与数据来源</p>
            </header>

            {/* 离场审计 */}
            <section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
                <h2 className="text-lg font-semibold text-blue-400 mb-1">离场审计 · 退料预警</h2>
                <p className="text-gray-400 text-sm mb-4">
                    工单完工后，线边仓仍有该工单对应物料的库存，说明存在未退料风险。
                </p>

                <h3 className="text-sm font-medium text-gray-300 mb-1">核心公式</h3>
                <FormulaBox>理论余料 = BOM总需求量 − 完工数量 × BOM单件用量</FormulaBox>
                <FormulaBox>偏差 = 实际库存 − 理论余料</FormulaBox>
                <p className="text-xs text-gray-500 mt-2">偏差 &gt; 0：账面超发，线边仓库存超出理论应剩，需立即盘点</p>

                <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-300 mb-1">字段说明</h3>
                    <MetricTable rows={[
                        ['BOM总需求量', 'IMES BOM', '计划数量 × BOM单件用量（sumQty 字段）'],
                        ['BOM单件用量', 'IMES BOM', '每生产1件产品需用量（qty 字段）'],
                        ['完工数量', 'IMES 工单', '实际完工件数（qtyDone 字段）'],
                        ['实际库存', 'SSRS 线边仓', '当前线边仓该物料的现存量（条码汇总）'],
                        ['高风险', '分析计算', '偏差 > 0.01 的组合，需立即核查实物'],
                    ]} />
                </div>
            </section>

            {/* 进场审计 */}
            <section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
                <h2 className="text-lg font-semibold text-yellow-400 mb-1">进场审计 · 超发发料</h2>
                <p className="text-gray-400 text-sm mb-4">
                    NWMS 实际扫码入线边仓的数量，超出备料单计划发料数量，说明存在超发风险。
                </p>

                <h3 className="text-sm font-medium text-gray-300 mb-1">核心公式</h3>
                <FormulaBox>超发量 = 实际发料量 − 计划发料量</FormulaBox>
                <FormulaBox>超发率 = 超发量 ÷ 计划发料量 × 100%</FormulaBox>

                <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-300 mb-1">字段说明</h3>
                    <MetricTable rows={[
                        ['计划发料量', 'NWMS 备料单', '备料员创建备料单时录入的计划数量（demandQuantity）'],
                        ['实际发料量', 'NWMS 扫码明细', '仓库人员实际扫码入线边仓的数量（actualQuantity）'],
                        ['超发量', '分析计算', '实际 − 计划，> 0 即超发'],
                        ['超发率', '分析计算', '超发比例，用于评估偏差严重程度'],
                    ]} />
                </div>
            </section>

            {/* 数据来源 */}
            <section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
                <h2 className="text-lg font-semibold text-gray-300 mb-3">数据来源与同步频率</h2>
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2 pr-4 font-medium">系统</th>
                            <th className="text-left py-2 pr-4 font-medium">数据内容</th>
                            <th className="text-left py-2 font-medium">同步频率</th>
                        </tr>
                    </thead>
                    <tbody className="text-gray-300">
                        <tr className="border-b border-gray-800">
                            <td className="py-2 pr-4 font-medium text-white">IMES</td>
                            <td className="py-2 pr-4">工单状态、BOM 明细</td>
                            <td className="py-2 text-green-400">每日 6–22 点整点</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                            <td className="py-2 pr-4 font-medium text-white">SSRS</td>
                            <td className="py-2 pr-4">线边仓库存（条码级）</td>
                            <td className="py-2 text-green-400">每日 6–22 点整点</td>
                        </tr>
                        <tr>
                            <td className="py-2 pr-4 font-medium text-white">NWMS</td>
                            <td className="py-2 pr-4">备料单发料明细</td>
                            <td className="py-2 text-yellow-400">每日凌晨 2 点全量</td>
                        </tr>
                    </tbody>
                </table>
            </section>
        </div>
    )
}
```

**Step 2: 验证页面**

浏览器访问 `http://localhost:5173/docs`，检查两个卡片、公式框、表格正常渲染。

**Step 3: Commit**

```bash
git add frontend/src/pages/MetricsDoc.tsx
git commit -m "feat: add MetricsDoc static page"
```

---

## Task 6: 实现数据明细页

**Files:**
- Modify: `frontend/src/pages/DetailPage.tsx`（替换占位内容）

**Step 1: 编写完整组件**

```tsx
// frontend/src/pages/DetailPage.tsx
import { useEffect, useState } from 'react'
import axios from 'axios'

interface Batch { batch_id: string; timestamp: string }
interface AlertRow {
    shop_order: string; material_code: string; material_desc: string
    warehouse: string; actual_inventory: number; theory_remain: number; deviation: number
}
interface IssueRow {
    demand_list_number: string; material_code: string; related_wo: string
    production_line: string; demand_qty: number; actual_qty: number; over_issue_qty: number
}

function DeviationBadge({ value }: { value: number }) {
    const cls = value > 0.01 ? 'text-red-400' : value < -0.01 ? 'text-blue-400' : 'text-gray-400'
    const prefix = value > 0 ? '+' : ''
    return <span className={`font-bold ${cls}`}>{prefix}{value.toFixed(2)}</span>
}

export default function DetailPage() {
    const [tab, setTab] = useState<'alert' | 'issue'>('alert')
    const [batches, setBatches] = useState<Batch[]>([])
    const [batchId, setBatchId] = useState('')
    const [query, setQuery] = useState('')
    const [alertRows, setAlertRows] = useState<AlertRow[]>([])
    const [issueRows, setIssueRows] = useState<IssueRow[]>([])
    const [chip, setChip] = useState<'all' | 'risk' | 'over' | 'under'>('all')
    const [loading, setLoading] = useState(false)

    // 加载批次列表
    useEffect(() => {
        axios.get<Batch[]>('/api/batches').then(res => {
            setBatches(res.data)
            if (res.data.length > 0) setBatchId(res.data[0].batch_id)
        })
    }, [])

    // 加载明细数据
    useEffect(() => {
        if (!batchId) return
        setLoading(true)
        const params = { batch_id: batchId, q: query }
        Promise.all([
            axios.get<AlertRow[]>('/api/alerts/list', { params }),
            axios.get<IssueRow[]>('/api/issues/list', { params }),
        ]).then(([a, i]) => {
            setAlertRows(a.data)
            setIssueRows(i.data)
        }).finally(() => setLoading(false))
    }, [batchId, query])

    // 切换 Tab 时重置 chip
    const switchTab = (t: 'alert' | 'issue') => { setTab(t); setChip('all') }

    const filteredAlerts = chip === 'risk' ? alertRows.filter(r => r.deviation > 0.01) : alertRows
    const filteredIssues = chip === 'over'
        ? issueRows.filter(r => r.over_issue_qty > 0.01)
        : chip === 'under' ? issueRows.filter(r => r.over_issue_qty < -0.01)
        : issueRows

    return (
        <div className="space-y-4">
            <header>
                <h1 className="text-2xl font-bold text-white">数据明细</h1>
                <p className="text-gray-400 text-sm mt-1">按工单/物料编号溯源作业记录</p>
            </header>

            {/* 顶部控件 */}
            <div className="flex items-center gap-3 flex-wrap">
                <select
                    value={batchId}
                    onChange={e => setBatchId(e.target.value)}
                    className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                >
                    {batches.map(b => (
                        <option key={b.batch_id} value={b.batch_id}>
                            {new Date(b.timestamp).toLocaleString()} ({b.batch_id})
                        </option>
                    ))}
                </select>
                <input
                    type="text"
                    placeholder="搜索工单号 / 物料编号 / 备料单号..."
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    className="flex-1 min-w-48 bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 placeholder-gray-500"
                />
                {loading && <span className="text-blue-400 text-sm animate-pulse">加载中...</span>}
            </div>

            {/* Tab 切换 */}
            <div className="flex gap-1 border-b border-gray-800">
                {(['alert', 'issue'] as const).map(t => (
                    <button
                        key={t}
                        onClick={() => switchTab(t)}
                        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                            tab === t
                                ? 'border-blue-500 text-blue-400'
                                : 'border-transparent text-gray-500 hover:text-gray-300'
                        }`}
                    >
                        {t === 'alert' ? `离场审计（${alertRows.length}）` : `进场审计（${issueRows.length}）`}
                    </button>
                ))}
            </div>

            {/* 快捷筛选 Chips */}
            <div className="flex gap-2">
                {tab === 'alert' ? (
                    <>
                        <Chip active={chip === 'all'} onClick={() => setChip('all')}>全部</Chip>
                        <Chip active={chip === 'risk'} onClick={() => setChip('risk')} color="red">仅高风险（偏差&gt;0）</Chip>
                    </>
                ) : (
                    <>
                        <Chip active={chip === 'all'} onClick={() => setChip('all')}>全部</Chip>
                        <Chip active={chip === 'over'} onClick={() => setChip('over')} color="red">仅超发</Chip>
                        <Chip active={chip === 'under'} onClick={() => setChip('under')} color="blue">少发</Chip>
                    </>
                )}
            </div>

            {/* 表格 */}
            {tab === 'alert' ? (
                <AlertTable rows={filteredAlerts} />
            ) : (
                <IssueTable rows={filteredIssues} />
            )}
        </div>
    )
}

function Chip({ active, onClick, color = 'blue', children }: {
    active: boolean; onClick: () => void; color?: 'blue' | 'red'; children: React.ReactNode
}) {
    const base = 'px-3 py-1 text-xs rounded-full border transition-colors cursor-pointer'
    const activeStyle = color === 'red'
        ? 'bg-red-900/40 border-red-500 text-red-400'
        : 'bg-blue-900/40 border-blue-500 text-blue-400'
    const inactiveStyle = 'bg-transparent border-gray-700 text-gray-400 hover:border-gray-500'
    return (
        <button className={`${base} ${active ? activeStyle : inactiveStyle}`} onClick={onClick}>
            {children}
        </button>
    )
}

function AlertTable({ rows }: { rows: AlertRow[] }) {
    if (rows.length === 0) return <Empty />
    return (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm text-left text-gray-300">
                <thead className="bg-gray-800 text-gray-400 text-xs uppercase">
                    <tr>
                        {['工单号', '物料编号', '物料描述', '线边仓', '实际库存', '理论余料', '偏差'].map(h => (
                            <th key={h} className="px-4 py-3">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                            <td className="px-4 py-3 font-medium text-white">{r.shop_order}</td>
                            <td className="px-4 py-3">{r.material_code}</td>
                            <td className="px-4 py-3 max-w-xs truncate" title={r.material_desc}>{r.material_desc}</td>
                            <td className="px-4 py-3">{r.warehouse}</td>
                            <td className="px-4 py-3">{r.actual_inventory?.toFixed(2)}</td>
                            <td className="px-4 py-3">{r.theory_remain?.toFixed(2) ?? '-'}</td>
                            <td className="px-4 py-3"><DeviationBadge value={r.deviation ?? 0} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function IssueTable({ rows }: { rows: IssueRow[] }) {
    if (rows.length === 0) return <Empty />
    return (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm text-left text-gray-300">
                <thead className="bg-gray-800 text-gray-400 text-xs uppercase">
                    <tr>
                        {['备料单号', '物料编号', '关联工单', '产线', '计划发料量', '实际发料量', '超发量'].map(h => (
                            <th key={h} className="px-4 py-3">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                            <td className="px-4 py-3 font-medium text-white">{r.demand_list_number}</td>
                            <td className="px-4 py-3">{r.material_code}</td>
                            <td className="px-4 py-3">{r.related_wo || '-'}</td>
                            <td className="px-4 py-3">{r.production_line || '-'}</td>
                            <td className="px-4 py-3">{r.demand_qty?.toFixed(2)}</td>
                            <td className="px-4 py-3">{r.actual_qty?.toFixed(2)}</td>
                            <td className="px-4 py-3"><DeviationBadge value={r.over_issue_qty ?? 0} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function Empty() {
    return <p className="text-center text-gray-500 py-12 text-sm">暂无数据</p>
}
```

**Step 2: 验证页面**

浏览器访问 `http://localhost:5173/detail`，检查：
- 批次下拉有数据
- 搜索框输入触发过滤
- Tab 切换正常
- Chip 筛选有效
- 表格数据正常渲染

**Step 3: Commit**

```bash
git add frontend/src/pages/DetailPage.tsx
git commit -m "feat: add DetailPage with two-tab filterable tables"
```

---

## 验收清单

- [ ] 左侧导航栏常驻，三个页面路由跳转正常
- [ ] 仪表盘页与原功能完全一致
- [ ] 指标说明页两个卡片正常展示，公式可读
- [ ] 数据明细页批次下拉、关键字搜索、Chip 筛选均正常
- [ ] 离场审计表格偏差列颜色正确（红/灰/蓝）
- [ ] 进场审计表格超发量列颜色正确
- [ ] `npm run build` 无 TypeScript 错误
