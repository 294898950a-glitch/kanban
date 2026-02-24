import { useEffect, useState, useRef } from 'react'
import * as echarts from 'echarts'
import axios from 'axios'

interface KPISummary {
    batch_id: string;
    timestamp: string;
    alert_group_count: number;
    high_risk_count: number;
    over_issue_lines: number;
    avg_aging_hours: number;
    confirmed_alert_count: number;
    unmatched_current_count: number;
    legacy_count: number;
}

interface AgingDistribution {
    le1: number;
    d1_3: number;
    d3_7: number;
    d7_14: number;
    d14_30: number;
    gt30: number;
}

interface KPITrend {
    timestamp: string;
    alert_group_count: number;
    high_risk_count: number;
    confirmed_alert_count: number;
    over_issue_lines: number;
    avg_aging_hours: number;
}

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

interface IssueTop {
    material_code: string;
    production_line: string;
    related_wo: string;
    plan_issue_date: string;
    demand_qty: number;
    actual_qty: number;
    over_issue_qty: number;
    over_issue_rate: number;
    bom_demand_qty: number;
    over_vs_bom_rate: number;
}

// 统一6档颜色配置（深绿→黄绿→琥珀→深橙→红→暗红）
const AGING_BANDS = [
    { key: 'le1' as const, label: '≤1天', title: '健康', bg: '#15803d', text: 'text-green-400' },
    { key: 'd1_3' as const, label: '1-3天', title: '观察中', bg: '#65a30d', text: 'text-lime-400' },
    { key: 'd3_7' as const, label: '3-7天', title: '开始关注', bg: '#d97706', text: 'text-amber-400' },
    { key: 'd7_14' as const, label: '7-14天', title: '需跟进', bg: '#c2410c', text: 'text-orange-500' },
    { key: 'd14_30' as const, label: '14-30天', title: '滞留风险', bg: '#dc2626', text: 'text-red-400' },
    { key: 'gt30' as const, label: '>30天', title: '严重滞留', bg: '#7f1d1d', text: 'text-rose-400' },
]

function AgingBadgeSmall({ days }: { days: number }) {
    if (days < 0) return <span className="text-gray-500 text-[10px]">-</span>
    const band =
        days <= 1 ? AGING_BANDS[0] :
            days <= 3 ? AGING_BANDS[1] :
                days <= 7 ? AGING_BANDS[2] :
                    days <= 14 ? AGING_BANDS[3] :
                        days <= 30 ? AGING_BANDS[4] :
                            AGING_BANDS[5]
    return <span className={`text-[10px] ${band.text}`}>{Math.floor(days)}天</span>
}

function Dashboard() {
    const [kpi, setKpi] = useState<KPISummary | null>(null)
    const [alerts, setAlerts] = useState<AlertTop[]>([])
    const [issues, setIssues] = useState<IssueTop[]>([])
    const [agingDist, setAgingDist] = useState<AgingDistribution | null>(null)
    const trendChartRef = useRef<HTMLDivElement>(null)
    const agingChartRef = useRef<HTMLDivElement>(null)
    const [loading, setLoading] = useState(true)
    const [excludeCommon, setExcludeCommon] = useState(false)

    // 退料预警排序
    const [alertSort, setAlertSort] = useState<{ key: 'actual_inventory' | 'aging_days', dir: 1 | -1 }>({ key: 'actual_inventory', dir: -1 })
    // 超发预警排序
    const [issueSort, setIssueSort] = useState<{ key: keyof IssueTop, dir: 1 | -1 }>({ key: 'over_issue_qty', dir: -1 })

    const fetchData = async () => {
        try {
            setLoading(true)
            // 使用相对路径，由于 vite.config.ts 已经配置了代理 /api
            const [kpiRes, alertsRes, issuesRes, trendRes, agingRes] = await Promise.all([
                axios.get<KPISummary>('/api/kpi/summary', { params: { exclude_common: excludeCommon } }),
                axios.get<AlertTop[]>('/api/alerts/top10', { params: { exclude_common: excludeCommon } }),
                axios.get<IssueTop[]>('/api/issues/top5'),
                axios.get<KPITrend[]>('/api/kpi/trend', { params: { exclude_common: excludeCommon } }),
                axios.get<AgingDistribution>('/api/kpi/aging-distribution')
            ])

            setKpi(kpiRes.data)
            setAlerts(alertsRes.data)
            setIssues(issuesRes.data)
            setAgingDist(agingRes.data)

            renderTrendChart(trendRes.data)
            renderAgingChart(trendRes.data)
        } catch (e) {
            console.error("Failed to fetch data", e)
        } finally {
            setLoading(false)
        }
    }

    const renderTrendChart = (trendData: KPITrend[]) => {
        if (!trendChartRef.current) return
        const chart = echarts.getInstanceByDom(trendChartRef.current) || echarts.init(trendChartRef.current)

        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis'
            },
            legend: {
                data: ['退料预警总量', '当期退料预警', '超发预警行数'],
                textStyle: { color: '#fff' }
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: trendData.map(d => d.timestamp),
                axisLabel: { color: '#ccc' }
            },
            yAxis: {
                type: 'value',
                axisLabel: { color: '#ccc' },
                splitLine: { lineStyle: { color: '#333' } }
            },
            series: [
                {
                    name: '退料预警总量',
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.1 },
                    data: trendData.map(d => d.alert_group_count),
                    itemStyle: { color: '#60a5fa' }
                },
                {
                    name: '当期退料预警',
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.1 },
                    data: trendData.map(d => d.confirmed_alert_count),
                    itemStyle: { color: '#f87171' }
                },
                {
                    name: '超发预警行数',
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.1 },
                    data: trendData.map(d => d.over_issue_lines),
                    itemStyle: { color: '#fbbf24' }
                }
            ]
        })
    }

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

    useEffect(() => {
        fetchData()

        // 计算距墨西哥蒙特雷时间下一个整点的毫秒数
        const msUntilNextMonterreyHour = () => {
            const now = new Date()
            const parts = new Intl.DateTimeFormat('en-US', {
                timeZone: 'America/Monterrey',
                minute: 'numeric', second: 'numeric',
            }).formatToParts(now)
            const min = parseInt(parts.find(p => p.type === 'minute')!.value)
            const sec = parseInt(parts.find(p => p.type === 'second')!.value)
            const ms  = now.getMilliseconds()
            return (60 - min) * 60_000 - sec * 1000 - ms
        }

        // 每 5 分钟轮询一次，确保新批次数据最多 5 分钟内自动显示
        const pollInterval = setInterval(fetchData, 5 * 60_000)

        // 同时保留蒙特雷整点对齐（不影响轮询）
        let hourlyInterval: ReturnType<typeof setInterval>
        const timeout = setTimeout(() => {
            fetchData()
            hourlyInterval = setInterval(fetchData, 3_600_000)
        }, msUntilNextMonterreyHour())

        // 窗口尺寸变化重绘
        const handleResize = () => {
            if (trendChartRef.current) echarts.getInstanceByDom(trendChartRef.current)?.resize()
            if (agingChartRef.current) echarts.getInstanceByDom(agingChartRef.current)?.resize()
        }
        window.addEventListener('resize', handleResize)

        return () => {
            clearInterval(pollInterval)
            clearTimeout(timeout)
            clearInterval(hourlyInterval)
            window.removeEventListener('resize', handleResize)
        }
    }, [excludeCommon])

    const sortedAlerts = [...alerts].sort((a, b) =>
        ((a[alertSort.key] ?? 0) - (b[alertSort.key] ?? 0)) * alertSort.dir)

    const sortedIssues = [...issues].sort((a, b) => {
        const av = a[issueSort.key] as number ?? 0
        const bv = b[issueSort.key] as number ?? 0
        return (av - bv) * issueSort.dir
    })

    const toggleAlertSort = (key: typeof alertSort.key) =>
        setAlertSort(s => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : -1 }))

    const toggleIssueSort = (key: keyof IssueTop) =>
        setIssueSort(s => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : -1 }))

    const sortIcon = (key: string, current: string, dir: 1 | -1) =>
        key === current ? (dir === -1 ? ' ↓' : ' ↑') : ' ↕'

    return (
        <div className="p-6">
            {/* 头部标题区 */}
            <header className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gradient mb-2">墨工厂物料流转审计仪表盘</h1>
                    <p className="text-gray-400 text-sm">
                        基于 IMES / NWMS / SSRS 数据融合监控 | 最后更新:&nbsp;
                        {kpi ? (() => {
                            const d = new Date(kpi.timestamp)
                            const cn = d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
                            const mx = d.toLocaleString('zh-CN', { timeZone: 'America/Monterrey', hour12: false })
                            return <><span title="中国标准时间 (CST)">🇨🇳 {cn}</span><span className="mx-2 text-gray-600">|</span><span title="蒙特雷时间 (CST-6/CDT-5)">🇲🇽 {mx}</span></>
                        })() : 'Loading...'}
                        {loading && <span className="ml-2 text-blue-400 animate-pulse">(刷新中...)</span>}
                    </p>
                </div>
                <button
                    onClick={fetchData}
                    className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg transition-colors font-medium text-sm flex items-center"
                >
                    <svg className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                    手动刷新
                </button>
            </header>

            {/* 核心指标卡片区 */}
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
                {/* 1. 当期退料预警 */}
                <div className="glass-panel p-5 border-l-4 border-l-red-500 animate-fade-in">
                    <h3 className="text-gray-400 text-xs font-medium mb-1">当期退料预警</h3>
                    <div className="text-2xl font-bold text-red-400">{kpi?.confirmed_alert_count ?? '-'}</div>
                    <p className="text-[10px] text-gray-500 mt-1">完工+已匹配+仍有库存</p>
                </div>
                {/* 2. 工单范围外库存 */}
                <div className="glass-panel p-5 border-l-4 border-l-orange-500 animate-fade-in" style={{ animationDelay: '100ms' }}>
                    <h3 className="text-gray-400 text-xs font-medium mb-1">工单范围外库存</h3>
                    <div className="text-2xl font-bold text-orange-400">{kpi?.unmatched_current_count ?? '-'}</div>
                    <p className="text-[10px] text-gray-500 mt-1">接收≥2026但关联未完工或无工单</p>
                </div>
                {/* 3. 历史遗留库存 */}
                <div className="glass-panel p-5 border-l-4 border-l-gray-500 animate-fade-in" style={{ animationDelay: '200ms' }}>
                    <h3 className="text-gray-400 text-xs font-medium mb-1">历史遗留库存</h3>
                    <div className="text-2xl font-bold text-gray-400">{kpi?.legacy_count ?? '-'}</div>
                    <p className="text-[10px] text-gray-500 mt-1">接收&lt;2026或无日期记录</p>
                </div>
                {/* 4. 进场：超发预警 */}
                <div className="glass-panel p-5 border-l-4 border-l-yellow-500 animate-fade-in" style={{ animationDelay: '300ms' }}>
                    <h3 className="text-gray-400 text-xs font-medium mb-1">进场：超发预警</h3>
                    <div className="text-2xl font-bold text-yellow-500">{kpi?.over_issue_lines ?? '-'}</div>
                    <p className="text-[10px] text-gray-500 mt-1">实际发料超BOM需求</p>
                </div>
                {/* 5. 当期平均库龄 */}
                <div className="glass-panel p-5 border-l-4 border-l-purple-500 animate-fade-in" style={{ animationDelay: '400ms' }}>
                    <h3 className="text-gray-400 text-xs font-medium mb-1">当期平均库龄</h3>
                    <div className="text-2xl font-bold text-purple-400">{kpi?.avg_aging_hours ?? '-'} <span className="text-sm">h</span></div>
                    <p className="text-[10px] text-gray-500 mt-1">基于当期退料预警池计算</p>
                </div>
            </div>

            {/* 库龄分布色带 */}
            {agingDist && kpi && (
                <div className="glass-panel p-4 mb-6 animate-fade-in" style={{ animationDelay: '500ms' }}>
                    <h3 className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-2">
                        <span className="w-1 h-3 bg-purple-500 rounded"></span>
                        当期退料库龄分布 (天)
                    </h3>
                    {(() => {
                        const total = Object.values(agingDist).reduce((a, b) => a + b, 0) || 1
                        const active = AGING_BANDS.filter(band => agingDist[band.key] > 0).map(band => ({
                            ...band,
                            count: agingDist[band.key],
                            w: Math.max(8, (agingDist[band.key] / total) * 100),
                        }))
                        return (
                            <>
                                <div className="flex h-6 rounded overflow-hidden shadow-inner bg-gray-800 text-[10px] font-bold text-white text-center leading-6">
                                    {active.map(b => (
                                        <div key={b.key} style={{ width: `${b.w}%`, backgroundColor: b.bg }}
                                            className="hover:opacity-80 transition-opacity overflow-hidden"
                                            title={`${b.title}(${b.label}): ${b.count}`}>
                                            {b.count}
                                        </div>
                                    ))}
                                </div>
                                <div className="flex text-[10px] mt-1">
                                    {active.map(b => (
                                        <div key={b.key} style={{ width: `${b.w}%`, color: b.bg }}
                                            className="text-center leading-tight overflow-hidden">
                                            <div className="truncate">{b.title}</div>
                                            <div className="text-gray-600 truncate">{b.label}</div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )
                    })()}
                </div>
            )}

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
                <div className="glass-panel p-6 flex flex-col h-[500px]">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <h3 className="text-lg font-bold flex items-center text-red-400">
                                <span className="w-2 h-6 bg-red-500 rounded mr-3"></span>
                                退料预警（全量）
                            </h3>
                            <button
                                onClick={() => setExcludeCommon(v => !v)}
                                className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                                    excludeCommon
                                    ? 'bg-yellow-600 border-yellow-500 text-white'
                                    : 'bg-gray-700 border-gray-600 text-gray-300 hover:border-gray-400'
                                }`}
                            >
                                {excludeCommon ? '已剔除通用物料' : '含通用物料'}
                            </button>
                        </div>
                        <div className="flex gap-1 text-[10px]">
                            {(['actual_inventory', 'aging_days'] as const).map(k => (
                                <button key={k} onClick={() => toggleAlertSort(k)}
                                    className={`px-2 py-1 rounded border transition-colors ${alertSort.key === k ? 'border-red-500 text-red-400' : 'border-gray-700 text-gray-500 hover:text-gray-300'}`}>
                                    {k === 'actual_inventory' ? '库存量' : '库龄'}{sortIcon(k, alertSort.key, alertSort.dir)}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="overflow-y-auto pr-2 flex-1 min-h-0 space-y-2">
                        {alerts.length === 0 ? (
                            <p className="text-gray-500 text-sm text-center py-8">暂无退料预警</p>
                        ) : (
                            sortedAlerts.map((a, i) => (
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
                <div className="glass-panel p-6 lg:col-span-2 flex flex-col h-[500px]">
                    <h3 className="text-lg font-bold mb-4 flex items-center text-yellow-500 shrink-0">
                        <span className="w-2 h-6 bg-yellow-500 rounded mr-3"></span>
                        进场超发预警（全量）
                    </h3>
                    <div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
                        <table className="w-full table-fixed text-left text-xs text-gray-300">
                            <colgroup>
                                <col style={{ width: '120px' }} />
                                <col style={{ width: '80px' }} />
                                <col style={{ width: '96px' }} />
                                <col style={{ width: '66px' }} />
                                <col style={{ width: '52px' }} />
                                <col style={{ width: '52px' }} />
                                <col style={{ width: '60px' }} />
                                <col style={{ width: '72px' }} />
                            </colgroup>
                            <thead className="bg-gray-800 text-gray-400 sticky top-0 text-xs">
                                <tr>
                                    <th className="px-2 py-1.5 text-left rounded-tl">产线</th>
                                    <th className="px-2 py-1.5 text-left">物料编号</th>
                                    <th className="px-2 py-1.5 text-left">关联工单</th>
                                    <th className="px-2 py-1.5 text-left">计划日期</th>
                                    {(['demand_qty', 'actual_qty', 'over_issue_qty'] as const).map(k => (
                                        <th key={k} onClick={() => toggleIssueSort(k)}
                                            className="px-2 py-1.5 text-right cursor-pointer hover:text-white select-none">
                                            {k === 'demand_qty' ? '计划' : k === 'actual_qty' ? '实发' : '超发量'}
                                            {sortIcon(k, issueSort.key, issueSort.dir)}
                                        </th>
                                    ))}
                                    <th onClick={() => toggleIssueSort('over_vs_bom_rate')}
                                        title="超发率%(BOM口径)"
                                        className="px-2 py-1.5 text-right rounded-tr cursor-pointer hover:text-white select-none">
                                        超发率%{sortIcon('over_vs_bom_rate', issueSort.key, issueSort.dir)}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {issues.length === 0 ? (
                                    <tr>
                                        <td colSpan={8} className="px-4 py-8 text-center text-gray-500">暂无超发发料数据</td>
                                    </tr>
                                ) : (
                                    sortedIssues.map((issue, idx) => {
                                        const rateColor = (issue.over_vs_bom_rate ?? 0) > 50
                                            ? 'text-red-400' : (issue.over_vs_bom_rate ?? 0) > 20
                                                ? 'text-orange-400' : 'text-yellow-400'
                                        return (
                                            <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                                                <td className="px-2 py-1.5 truncate">{issue.production_line || '-'}</td>
                                                <td className="px-2 py-1.5 font-medium text-white truncate" title={issue.material_code}>{issue.material_code}</td>
                                                <td className="px-2 py-1.5 text-gray-400 truncate" title={issue.related_wo}>{issue.related_wo || '-'}</td>
                                                <td className="px-2 py-1.5 text-gray-400 truncate">{(issue.plan_issue_date || '').slice(0, 10) || '-'}</td>
                                                <td className="px-2 py-1.5 text-right">{issue.demand_qty?.toFixed(0)}</td>
                                                <td className="px-2 py-1.5 text-right">{issue.actual_qty?.toFixed(0)}</td>
                                                <td className="px-2 py-1.5 text-right font-bold text-yellow-400">+{issue.over_issue_qty?.toFixed(0)}</td>
                                                <td className={`px-2 py-1.5 text-right font-bold ${rateColor}`}>
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
        </div>
    )
}

export default Dashboard
