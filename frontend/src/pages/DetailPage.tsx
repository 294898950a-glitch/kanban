import { useEffect, useState } from 'react'
import axios from 'axios'

interface Batch { batch_id: string; timestamp: string }
interface AlertRow {
    shop_order: string; material_code: string; material_desc: string
    warehouse: string; actual_inventory: number; barcode_count: number;
    unit: string; aging_days: number;
    barcode_list: string[];
}
interface IssueRow {
    demand_list_number: string; material_code: string; related_wo: string
    production_line: string; plan_issue_date: string
    demand_qty: number; actual_qty: number; over_issue_qty: number
    over_issue_rate: number; bom_demand_qty: number; over_vs_bom_rate: number
}

function DeviationBadge({ value }: { value: number }) {
    const cls = value > 0.01 ? 'text-red-400' : value < -0.01 ? 'text-blue-400' : 'text-gray-400'
    const prefix = value > 0 ? '+' : ''
    return <span className={`font-bold ${cls}`}>{prefix}{value.toFixed(2)}</span>
}

// 与 Dashboard 统一的6档色阶（深绿→黄绿→琥珀→深橙→红→暗红）
const AGING_BANDS = [
    { maxDays: 1,   title: '健康',   bg: '#15803d', border: '#16a34a' },
    { maxDays: 3,   title: '观察中', bg: '#65a30d', border: '#84cc16' },
    { maxDays: 7,   title: '开始关注', bg: '#d97706', border: '#f59e0b' },
    { maxDays: 14,  title: '需跟进', bg: '#c2410c', border: '#ea580c' },
    { maxDays: 30,  title: '滞留风险', bg: '#dc2626', border: '#ef4444' },
    { maxDays: Infinity, title: '严重滞留', bg: '#7f1d1d', border: '#991b1b' },
]

function AgingBadge({ days }: { days: number }) {
    if (days < 0) return <span className="text-gray-500">-</span>
    const band = AGING_BANDS.find(b => days <= b.maxDays) ?? AGING_BANDS[AGING_BANDS.length - 1]
    return (
        <span
            className="px-2 py-0.5 whitespace-nowrap text-xs border rounded font-medium"
            style={{ backgroundColor: band.bg + '55', color: '#fff', borderColor: band.border }}
            title={`${days} 天`}
        >
            {days}d ({band.title})
        </span>
    )
}

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

export default function DetailPage() {
    const [tab, setTab] = useState<'alert' | 'issue'>('alert')
    const [batches, setBatches] = useState<Batch[]>([])
    const [batchId, setBatchId] = useState('')
    const [query, setQuery] = useState('')
    const [alertRows, setAlertRows] = useState<AlertRow[]>([])
    const [issueRows, setIssueRows] = useState<IssueRow[]>([])
    const [alertChip, setAlertChip] = useState<'all' | 'le3' | 'd3_7' | 'd7_14' | 'gt14'>('all')
    const [issueChip, setIssueChip] = useState<'all' | 'over' | 'under'>('all')
    const [issueSort, setIssueSort] = useState<{ key: keyof IssueRow; dir: 1 | -1 }>({ key: 'over_issue_qty', dir: -1 })
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

    // 初始化 URL 参数
    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const agingParam = urlParams.get('aging');
        if (agingParam && ['le3', 'd3_7', 'd7_14', 'gt14'].includes(agingParam)) {
            setTab('alert');
            setAlertChip(agingParam as any);
        }
    }, [])

    // 切换 Tab 时重置 chip
    const switchTab = (t: 'alert' | 'issue') => {
        setTab(t);
        if (t === 'alert') setAlertChip('all')
        else setIssueChip('all')
    }

    const filteredAlerts = alertRows.filter(r => {
        if (alertChip === 'all') return true
        if (r.aging_days < 0) return false
        if (alertChip === 'le3') return r.aging_days <= 3
        if (alertChip === 'd3_7') return r.aging_days > 3 && r.aging_days <= 7
        if (alertChip === 'd7_14') return r.aging_days > 7 && r.aging_days <= 14
        if (alertChip === 'gt14') return r.aging_days > 14
        return true
    })

    const filteredIssues = (() => {
        let rows = issueChip === 'over'
            ? issueRows.filter(r => r.over_issue_qty > 0.01)
            : issueChip === 'under' ? issueRows.filter(r => r.over_issue_qty < -0.01)
                : issueRows
        return [...rows].sort((a, b) => {
            const av = a[issueSort.key] ?? 0
            const bv = b[issueSort.key] ?? 0
            return av < bv ? -issueSort.dir : av > bv ? issueSort.dir : 0
        })
    })()

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
                    placeholder="搜索工单号 / 物料编号 / 条码 / 备料单号..."
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
                        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === t
                            ? 'border-blue-500 text-blue-400'
                            : 'border-transparent text-gray-500 hover:text-gray-300'
                            }`}
                    >
                        {t === 'alert' ? `离场审计（${alertRows.length}）` : `进场审计（${issueRows.length}）`}
                    </button>
                ))}
            </div>

            {/* 快捷筛选 Chips */}
            <div className="flex gap-2 mb-4">
                {tab === 'alert' ? (
                    <>
                        <Chip active={alertChip === 'all'} onClick={() => setAlertChip('all')}>全部</Chip>
                        <Chip active={alertChip === 'le3'} onClick={() => setAlertChip('le3')} color="green">≤3天</Chip>
                        <Chip active={alertChip === 'd3_7'} onClick={() => setAlertChip('d3_7')} color="yellow">3-7天</Chip>
                        <Chip active={alertChip === 'd7_14'} onClick={() => setAlertChip('d7_14')} color="orange">7-14天</Chip>
                        <Chip active={alertChip === 'gt14'} onClick={() => setAlertChip('gt14')} color="red">&gt;14天</Chip>
                    </>
                ) : (
                    <>
                        <Chip active={issueChip === 'all'} onClick={() => setIssueChip('all')}>全部</Chip>
                        <Chip active={issueChip === 'over'} onClick={() => setIssueChip('over')} color="red">仅超发</Chip>
                        <Chip active={issueChip === 'under'} onClick={() => setIssueChip('under')} color="blue">少发</Chip>
                    </>
                )}
            </div>

            {/* 表格 */}
            {tab === 'alert' ? (
                <AlertTable rows={filteredAlerts} />
            ) : (
                <IssueTable rows={filteredIssues} sort={issueSort} onSort={setIssueSort} />
            )}
        </div>
    )
}

function Chip({ active, onClick, color = 'blue', children }: {
    active: boolean; onClick: () => void; color?: 'blue' | 'red' | 'green' | 'yellow' | 'orange'; children: React.ReactNode
}) {
    const base = 'px-3 py-1 text-xs rounded-full border transition-colors cursor-pointer whitespace-nowrap'
    let activeStyle = ''
    if (color === 'red') activeStyle = 'bg-red-900/40 border-red-500 text-red-400'
    else if (color === 'green') activeStyle = 'bg-green-900/40 border-green-500 text-green-400'
    else if (color === 'yellow') activeStyle = 'bg-yellow-900/40 border-yellow-500 text-yellow-400'
    else if (color === 'orange') activeStyle = 'bg-orange-900/40 border-orange-500 text-orange-400'
    else activeStyle = 'bg-blue-900/40 border-blue-500 text-blue-400'

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
                        {['工单号', '物料编号', '物料描述', '线边仓', '实际库存', '单位', '库龄分析', '条码'].map(h => (
                            <th key={h} className="px-4 py-3 whitespace-nowrap">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                            <td className="px-4 py-3 font-medium text-white">{r.shop_order}</td>
                            <td className="px-4 py-3">{r.material_code}</td>
                            <td className="px-4 py-3 max-w-xs truncate" title={r.material_desc}>{r.material_desc}</td>
                            <td className="px-4 py-3 truncate max-w-[150px]" title={r.warehouse}>{r.warehouse}</td>
                            <td className="px-4 py-3 font-medium text-blue-400">{r.actual_inventory?.toFixed(2)}</td>
                            <td className="px-4 py-3 text-gray-500">{r.unit || '-'}</td>
                            <td className="px-4 py-3"><AgingBadge days={r.aging_days} /></td>
                            <td className="px-4 py-3 min-w-[120px]"><BarcodeCell list={r.barcode_list ?? []} count={r.barcode_count} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

type IssueSort = { key: keyof IssueRow; dir: 1 | -1 }

function IssueTable({ rows, sort, onSort }: { rows: IssueRow[]; sort: IssueSort; onSort: (s: IssueSort) => void }) {
    if (rows.length === 0) return <Empty />

    const cols: { label: string; key: keyof IssueRow }[] = [
        { label: '备料单号', key: 'demand_list_number' },
        { label: '物料编号', key: 'material_code' },
        { label: '关联工单', key: 'related_wo' },
        { label: '产线', key: 'production_line' },
        { label: '计划日期', key: 'plan_issue_date' },
        { label: 'BOM需求量', key: 'bom_demand_qty' },
        { label: '计划发料量', key: 'demand_qty' },
        { label: '实际发料量', key: 'actual_qty' },
        { label: '超发量', key: 'over_issue_qty' },
        { label: '超发率', key: 'over_issue_rate' },
        { label: '超BOM率', key: 'over_vs_bom_rate' },
    ]

    const handleSort = (key: keyof IssueRow) => {
        onSort(sort.key === key ? { key, dir: (sort.dir * -1) as 1 | -1 } : { key, dir: -1 })
    }

    const arrow = (key: keyof IssueRow) =>
        sort.key === key ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''

    const fmtRate = (v: number | null | undefined) =>
        (v == null || v === 0) ? '-' : `${v.toFixed(1)}%`

    return (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm text-left text-gray-300">
                <thead className="bg-gray-800 text-gray-400 text-xs uppercase">
                    <tr>
                        {cols.map(c => (
                            <th
                                key={c.key}
                                className="px-4 py-3 whitespace-nowrap cursor-pointer hover:text-white select-none"
                                onClick={() => handleSort(c.key)}
                            >
                                {c.label}{arrow(c.key)}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                            <td className="px-4 py-3 font-medium text-white">{r.demand_list_number}</td>
                            <td className="px-4 py-3">{r.material_code}</td>
                            <td className="px-4 py-3 whitespace-nowrap">{r.related_wo || '-'}</td>
                            <td className="px-4 py-3 whitespace-nowrap">{r.production_line || '-'}</td>
                            <td className="px-4 py-3 text-gray-500">{r.plan_issue_date || '-'}</td>
                            <td className="px-4 py-3">{r.bom_demand_qty > 0 ? r.bom_demand_qty.toFixed(2) : '-'}</td>
                            <td className="px-4 py-3">{r.demand_qty?.toFixed(2)}</td>
                            <td className="px-4 py-3">{r.actual_qty?.toFixed(2)}</td>
                            <td className="px-4 py-3"><DeviationBadge value={r.over_issue_qty ?? 0} /></td>
                            <td className="px-4 py-3 text-yellow-400">{fmtRate(r.over_issue_rate)}</td>
                            <td className="px-4 py-3 text-orange-400">{fmtRate(r.over_vs_bom_rate)}</td>
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
