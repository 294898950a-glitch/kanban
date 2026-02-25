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
                    系统<strong className="text-white">不依赖理论余料或偏差计算</strong>——
                    偏差会受提前合并送料、返工超耗、BOM 滞后等因素干扰，无法作为现场操作依据。
                </p>

                <h3 className="text-sm font-medium text-gray-300 mb-2">触发条件</h3>
                <FormulaBox>2026 年工单  ×  已完工  ×  线边仓仍有库存  →  退料预警</FormulaBox>

                <div className="mt-4 p-3 bg-gray-800 rounded-lg border border-gray-700">
                    <p className="text-xs text-gray-400">
                        <span className="text-yellow-400 font-medium">通用物料 Toggle：</span>
                        部分物料（辅料、共用件等）会跨工单共享，长期留存属正常现象。
                        页面右上角可切换「含通用物料 / 已剔除通用物料」两种口径，
                        剔除后的数字更能反映真实积压风险。通用物料白名单由管理员维护。
                    </p>
                </div>

                <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-300 mb-2">KPI 卡片说明</h3>
                    <MetricTable rows={[
                        ['当期退料预警', '分析计算', '匹配 2026 年工单 + 已完工 + 线边仓仍有库存，需立即退料处理；受通用物料 Toggle 影响'],
                        ['工单范围外库存', '分析计算', '接收时间≥2026 但关联工单不在 IMES 监控窗口，需人工核查归属'],
                        ['历史遗留库存', '分析计算', '接收时间<2026 或无记录的线边仓库存组合数（工单+物料），不计入预警但保留展示'],
                        ['进场：超发预警', '分析计算', 'NWMS 实际发料量超出计划发料量的行数，跨备料单汇总'],
                        ['当期平均库龄', '分析计算', '仅统计当期退料预警物料的平均滞留时长（小时）；受通用物料 Toggle 影响'],
                    ]} />
                </div>

                <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-300 mb-2">趋势图指标说明</h3>
                    <MetricTable rows={[
                        ['退料预警总量', '分析计算', '所有完工工单仍有库存的组合数，含当期 + 历史遗留中已完工部分（= 当期退料预警 + 遗留已完工预警）'],
                        ['当期退料预警', '分析计算', '退料预警总量的子集：仅限接收时间≥2026 且工单在监控窗口内的部分，差值即为历史遗留中的完工预警'],
                        ['超发预警行数', '分析计算', '与「进场：超发预警」KPI 卡片同一数值，在趋势图中展示历史变化'],
                        ['当期平均库龄', '分析计算', '与 KPI 卡片同一数值（小时），在专用趋势图中展示历史变化'],
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
                        ['工单号', 'SSRS / IMES', '生产工单编号，三表关联核心 Key'],
                        ['实际库存量', 'SSRS 线边仓', '该（工单, 物料）组合在线边仓的现存总量（所有条码汇总）'],
                        ['单位', 'SSRS 线边仓', '物料计量单位（EA / PCS / M 等）'],
                        ['条码数', 'SSRS 线边仓', '该组合对应的独立条码/批次数量'],
                        ['条码', 'SSRS 线边仓', '展开显示各条码编号，可追溯实物位置，支持关键字搜索'],
                        ['库龄', '分析计算', '当前时间 − 最早接收时间（天），颜色规则与色带一致'],
                    ]} />
                </div>

                <div className="mt-6">
                    <h3 className="text-sm font-medium text-gray-300 mb-2">物料用途状态</h3>
                    <p className="text-xs text-gray-400 mb-3">
                        每条线边仓库存基于其关联工单的当前状态，动态标注用途。明细页可按状态筛选；
                        仪表盘退料预警列表额外显示「复用」徽标。
                    </p>
                    <div className="space-y-2">
                        {[
                            {
                                chip: { bg: '#14532d55', color: '#4ade80', border: '#16a34a' },
                                label: '🟢 当前生产',
                                desc: '该物料的指定工单正在生产中（工单状态：Se ha iniciado la construcción）。物料处于正常在线状态，无需干预。',
                            },
                            {
                                chip: { bg: '#1e3a5f55', color: '#93c5fd', border: '#3b82f6' },
                                label: '🔵 即将生产',
                                desc: '指定工单已下发但尚未开工（工单状态：Se puede emitir）。物料已备好，等待开线。',
                            },
                            {
                                chip: { bg: '#7c2d1255', color: '#fb923c', border: '#c2410c' },
                                label: '🟠 已完工待退',
                                desc: '指定工单已完工，但线边仓仍有该物料库存。属于退料预警范围，需尽快退库。',
                            },
                            {
                                chip: { bg: '#14532d55', color: '#4ade80', border: '#16a34a' },
                                label: '🔄 当前工单复用',
                                desc: '工单已完工（本应退料），但该物料编号同时出现在某个在制工单的 BOM 中。可直接转给在制工单使用，无需走退库再发料流程，优先级低于纯退料行。',
                            },
                            {
                                chip: { bg: '#1e3a5f55', color: '#93c5fd', border: '#3b82f6' },
                                label: '🔄 下工单复用',
                                desc: '工单已完工（本应退料），但该物料编号出现在某个待开工工单的 BOM 中。可暂缓退料，等待下一工单开线后直接转用。',
                            },
                        ].map(({ chip, label, desc }) => (
                            <div key={label} className="flex items-start gap-3 p-3 bg-gray-800 rounded-lg">
                                <span className="shrink-0 mt-0.5 inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border"
                                    style={{ background: chip.bg, color: chip.color, borderColor: chip.border }}>
                                    {label}
                                </span>
                                <p className="text-xs text-gray-300 leading-relaxed">{desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* 进场审计 */}
            <section className="bg-gray-900 rounded-xl p-6 border border-gray-800">
                <h2 className="text-lg font-semibold text-yellow-400 mb-1">进场审计 · 超发发料</h2>
                <p className="text-gray-400 text-sm mb-4">
                    NWMS 实际扫码入线边仓的数量，超出计划发料量即为超发。
                    系统提供 <strong className="text-white">NWMS 口径</strong>（备料单计划量）和
                    <strong className="text-white"> BOM 口径</strong>（IMES 标准需求量）双维对比。
                </p>

                <h3 className="text-sm font-medium text-gray-300 mb-1">核心公式 — NWMS 口径</h3>
                <FormulaBox>超发量 = 实际发料量 − 计划发料量（demandQty）</FormulaBox>
                <FormulaBox>超发率 = 超发量 ÷ 计划发料量 × 100%</FormulaBox>

                <h3 className="text-sm font-medium text-gray-300 mt-4 mb-1">核心公式 — BOM 口径</h3>
                <FormulaBox>超发量(vs BOM) = 实际发料量 − BOM标准需求量（sumQty）</FormulaBox>
                <FormulaBox>超发率%(vs BOM) = 超发量(vs BOM) ÷ BOM标准需求量 × 100%</FormulaBox>
                <p className="text-xs text-gray-500 mt-2">
                    BOM 口径使用 IMES 工单的理论用量作为基准，不受备料员填单误影响；
                    若 BOM 无数据则显示«(BOM无数据)»。
                </p>

                <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-300 mb-1">字段说明</h3>
                    <MetricTable rows={[
                        ['备料单号', 'NWMS 备料单', 'NWMS 系统的发料指令单据编号（instructionDocId）'],
                        ['物料编号', 'NWMS / IMES', '发料物料的编号，可与 BOM 和线边仓库存关联'],
                        ['关联工单', 'NWMS 备料单', '该备料单关联的生产工单号，可能含多个（逗号分隔）'],
                        ['产线', 'NWMS 备料单', '发料目标产线名称'],
                        ['计划发料日期', 'NWMS 备料单', '备料单计划执行日期（ppStartTime），用于判断发料是否滞后'],
                        ['BOM标准需求量', 'IMES BOM', '工单计划量 × BOM单件用量（sumQty），不受备料员填单影响的客观基准'],
                        ['计划发料量', 'NWMS 备料单', '备料员录入的计划数量（demandQuantity）'],
                        ['实际发料量', 'NWMS 扫码明细', '仓库人员实际扫码入线边仓的数量（actualQuantity）'],
                        ['超发量', '分析计算', '实际 − 计划，> 0 即超发（NWMS 口径）'],
                        ['超发率%', '分析计算', 'NWMS 口径超发比例，用于评估偏差严重程度'],
                        ['超BOM率%', '分析计算', '实际发料量相对 BOM 标准需求量的超出比例，更客观'],
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
                            <td className="py-2 pr-4">工单状态（每次同步）、BOM 明细（每日晨间）</td>
                            <td className="py-2 text-green-400">06 / 10 / 14 / 18 / 22 CST</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                            <td className="py-2 pr-4 font-medium text-white">SSRS</td>
                            <td className="py-2 pr-4">线边仓库存（条码级）</td>
                            <td className="py-2 text-green-400">06 / 10 / 14 / 18 / 22 CST</td>
                        </tr>
                        <tr>
                            <td className="py-2 pr-4 font-medium text-white">NWMS</td>
                            <td className="py-2 pr-4">备料单发料明细（2026年起）</td>
                            <td className="py-2 text-green-400">06 / 10 / 14 / 18 / 22 CST</td>
                        </tr>
                    </tbody>
                </table>
            </section>
        </div>
    )
}
