export function WoStatusChip({ label, reuse, isLegacy }: { label: string; reuse?: string; isLegacy?: number }) {
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
    // 无 IMES 工单匹配的库存（历史遗留或工单范围外）
    if (isLegacy === 1) return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#1f2937', color: '#6b7280', border: '1px solid #374151' }}>
            📦 历史遗留
        </span>
    )
    return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#1f2937', color: '#9ca3af', border: '1px solid #374151' }}>
            ❓ 工单外
        </span>
    )
}
