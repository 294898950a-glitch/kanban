# 前端设计系统（Frontend Design System）

> 本文档提取自 LMT-Kanban 项目前端，供新报表页面保持风格统一。
> 技术栈：React 18 + Vite + TailwindCSS + ECharts + Axios

---

## 1. 全局配色

### 背景层级

```
页面背景:    bg-gray-950   (#030712)
卡片/面板:   glass-panel   (rgba(31,41,55,0.7) + blur)
表格行悬停:  hover:bg-gray-800/50
表头背景:    bg-gray-800   (#1f2937)
输入框背景:  bg-gray-800   (#1f2937)
分割线:      border-gray-800 / border-gray-700
```

### 语义颜色

```
主要文字:    text-white
次要文字:    text-gray-300 / text-gray-400
占位/禁用:   text-gray-500 / text-gray-600

危险/高风险: text-red-400     border-l-red-500    (#f87171)
警告/超发:   text-yellow-400  border-l-yellow-500 (#fbbf24)
提示/进行中: text-orange-400  border-l-orange-500 (#fb923c)
正常/安全:   text-blue-400    border-l-blue-500   (#60a5fa)
次要/遗留:   text-gray-400    border-l-gray-500
趋势/时序:   text-purple-400  border-l-purple-500 (#a855f7)
```

### ECharts 系列颜色

```
折线图1 (退料预警总量):  #60a5fa  (blue-400)
折线图2 (当期退料预警):  #f87171  (red-400)
折线图3 (超发预警行数):  #fbbf24  (amber-400)
折线图4 (平均库龄):      #a855f7  (purple-500) — 单独图表时使用
```

### 库龄6档颜色（深绿→暗红）

```javascript
const AGING_BANDS = [
    { maxDays: 1,        label: '≤1天',   title: '健康',    bg: '#15803d', border: '#16a34a', text: 'text-green-400'  },
    { maxDays: 3,        label: '1-3天',  title: '观察中',  bg: '#65a30d', border: '#84cc16', text: 'text-lime-400'   },
    { maxDays: 7,        label: '3-7天',  title: '开始关注', bg: '#d97706', border: '#f59e0b', text: 'text-amber-400'  },
    { maxDays: 14,       label: '7-14天', title: '需跟进',  bg: '#c2410c', border: '#ea580c', text: 'text-orange-500' },
    { maxDays: 30,       label: '14-30天',title: '滞留风险', bg: '#dc2626', border: '#ef4444', text: 'text-red-400'    },
    { maxDays: Infinity, label: '>30天',  title: '严重滞留', bg: '#7f1d1d', border: '#991b1b', text: 'text-rose-400'   },
]
```

---

## 2. 全局样式类（index.css）

```css
/* 玻璃拟态卡片 — 所有面板统一使用 className="glass-panel" */
.glass-panel {
  background: rgba(31, 41, 55, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
  box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
}

/* 渐变标题 — 页面主标题使用 className="text-gradient" */
.text-gradient {
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-image: linear-gradient(to right, #60a5fa, #3b82f6);
}
```

---

## 3. 页面布局

### 根布局（App.tsx）

```tsx
<div className="flex min-h-screen bg-gray-950 text-white">
    <NavRail />                           {/* 左侧 240px 固定导航 */}
    <main className="ml-60 flex-1 p-6 overflow-auto">
        {/* 页面内容 */}
    </main>
</div>
```

### 页面标准头部

```tsx
<header className="flex justify-between items-center mb-8">
    <div>
        <h1 className="text-3xl font-bold text-gradient mb-2">页面标题</h1>
        <p className="text-gray-400 text-sm">副标题描述</p>
    </div>
    <button
        onClick={fetchData}
        className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg
                   transition-colors font-medium text-sm flex items-center"
    >
        手动刷新
    </button>
</header>
```

### 简单页面头部（无刷新按钮）

```tsx
<header>
    <h1 className="text-2xl font-bold text-white">页面标题</h1>
    <p className="text-gray-400 text-sm mt-1">描述文字</p>
</header>
```

---

## 4. KPI 卡片

```tsx
{/* 标准 KPI 卡片 — border-l-4 颜色按语义选择 */}
<div className="glass-panel p-5 border-l-4 border-l-red-500 animate-fade-in">
    <h3 className="text-gray-400 text-xs font-medium mb-1">卡片标题</h3>
    <div className="text-2xl font-bold text-red-400">{value ?? '-'}</div>
    <p className="text-[10px] text-gray-500 mt-1">说明文字</p>
</div>

{/* 5卡片网格 */}
<div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
    {/* 动画延迟：style={{ animationDelay: '100ms' }}，依次 0/100/200/300/400ms */}
</div>
```

---

## 5. 面板标题（带色块装饰）

```tsx
{/* 面板内标题统一用左侧色块 */}
<h3 className="text-lg font-bold mb-4 flex items-center">
    <span className="w-2 h-6 bg-blue-500 rounded mr-3"></span>
    标题文字
</h3>

{/* 带颜色的标题 */}
<h3 className="text-lg font-bold mb-4 flex items-center text-red-400">
    <span className="w-2 h-6 bg-red-500 rounded mr-3"></span>
    退料预警（全量）
</h3>
```

---

## 6. 表格

### 标准数据表格

```tsx
<div className="overflow-x-auto rounded-lg border border-gray-800">
    <table className="w-full text-sm text-left text-gray-300">
        <thead className="bg-gray-800 text-gray-400 text-xs uppercase">
            <tr>
                <th className="px-4 py-3 whitespace-nowrap">列标题</th>
                {/* 可排序列 */}
                <th
                    className="px-4 py-3 whitespace-nowrap cursor-pointer hover:text-white select-none"
                    onClick={() => handleSort('field_key')}
                >
                    列标题{sort.key === 'field_key' ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}
                </th>
            </tr>
        </thead>
        <tbody>
            {rows.map((r, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 font-medium text-white">{r.primary_field}</td>
                    <td className="px-4 py-3">{r.field}</td>
                    <td className="px-4 py-3 text-right text-blue-400">{r.number?.toFixed(2)}</td>
                </tr>
            ))}
        </tbody>
    </table>
</div>
```

### 仪表盘内嵌固定宽度表格（含滚动）

```tsx
<div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
    <table className="w-full table-fixed text-left text-xs text-gray-300">
        <colgroup>
            <col style={{ width: '120px' }} />
            <col style={{ width: '80px' }} />
            {/* ... */}
        </colgroup>
        <thead className="bg-gray-800 text-gray-400 sticky top-0 text-xs">
            {/* sticky 表头 */}
        </thead>
    </table>
</div>
```

### 排序状态管理

```typescript
const [sort, setSort] = useState<{ key: keyof Row; dir: 1 | -1 }>({ key: 'qty', dir: -1 })

const handleSort = (key: keyof Row) =>
    setSort(s => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : -1 }))

const sortedRows = [...rows].sort((a, b) => {
    const av = a[sort.key] as number ?? 0
    const bv = b[sort.key] as number ?? 0
    return (av - bv) * sort.dir
})
```

---

## 7. Chip 筛选组件

```tsx
function Chip({ active, onClick, color = 'blue', children }: {
    active: boolean; onClick: () => void
    color?: 'blue' | 'red' | 'green' | 'yellow' | 'orange'
    children: React.ReactNode
}) {
    const base = 'px-3 py-1 text-xs rounded-full border transition-colors cursor-pointer whitespace-nowrap'
    const activeMap = {
        red:    'bg-red-900/40 border-red-500 text-red-400',
        green:  'bg-green-900/40 border-green-500 text-green-400',
        yellow: 'bg-yellow-900/40 border-yellow-500 text-yellow-400',
        orange: 'bg-orange-900/40 border-orange-500 text-orange-400',
        blue:   'bg-blue-900/40 border-blue-500 text-blue-400',
    }
    const inactiveStyle = 'bg-transparent border-gray-700 text-gray-400 hover:border-gray-500'
    return (
        <button className={`${base} ${active ? activeMap[color] : inactiveStyle}`} onClick={onClick}>
            {children}
        </button>
    )
}

{/* 使用 */}
<div className="flex gap-2 mb-4">
    <Chip active={chip === 'all'}  onClick={() => setChip('all')}>全部</Chip>
    <Chip active={chip === 'high'} onClick={() => setChip('high')} color="red">高风险</Chip>
</div>
```

---

## 8. 表单控件

```tsx
{/* 下拉选择 */}
<select
    value={value}
    onChange={e => setValue(e.target.value)}
    className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2
               focus:outline-none focus:border-blue-500"
>
    <option value="x">选项</option>
</select>

{/* 文本搜索框 */}
<input
    type="text"
    placeholder="搜索..."
    value={query}
    onChange={e => setQuery(e.target.value)}
    className="flex-1 min-w-48 bg-gray-800 border border-gray-700 text-white text-sm rounded-lg
               px-3 py-2 focus:outline-none focus:border-blue-500 placeholder-gray-500"
/>
```

---

## 9. ECharts 折线图（暗色主题）

```typescript
const renderChart = (ref: React.RefObject<HTMLDivElement>, data: any[]) => {
    if (!ref.current) return
    const chart = echarts.getInstanceByDom(ref.current) || echarts.init(ref.current)
    chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis' },
        legend: { textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: data.map(d => d.timestamp),
            axisLabel: { color: '#ccc' },
        },
        yAxis: {
            type: 'value',
            axisLabel: { color: '#ccc' },
            splitLine: { lineStyle: { color: '#333' } },
        },
        series: [{
            name: '系列名',
            type: 'line',
            smooth: true,
            areaStyle: { opacity: 0.1 },
            data: data.map(d => d.value),
            itemStyle: { color: '#60a5fa' },
        }],
    })
}

// 容器
<div ref={chartRef} className="w-full h-80"></div>

// 窗口 resize 响应
window.addEventListener('resize', () => {
    echarts.getInstanceByDom(ref.current!)?.resize()
})
```

---

## 10. 数据获取模式

```typescript
const [data, setData] = useState<T | null>(null)
const [loading, setLoading] = useState(true)

const fetchData = async () => {
    try {
        setLoading(true)
        const res = await axios.get<T>('/api/your-endpoint')
        setData(res.data)
    } catch (e) {
        console.error('Failed to fetch', e)
    } finally {
        setLoading(false)
    }
}

useEffect(() => { fetchData() }, [])

{/* Loading 指示 */}
{loading && <span className="text-blue-400 text-sm animate-pulse">加载中...</span>}

{/* 空数据 */}
{!data && <p className="text-center text-gray-500 py-12 text-sm">暂无数据</p>}
```

---

## 11. 自动刷新（对齐蒙特雷整点）

```typescript
useEffect(() => {
    fetchData()

    // 5 分钟轮询（确保新批次最多 5 分钟内自动出现）
    const pollInterval = setInterval(fetchData, 5 * 60_000)

    // 对齐蒙特雷整点刷新
    const msUntilNext = () => {
        const now = new Date()
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/Monterrey',
            minute: 'numeric', second: 'numeric',
        }).formatToParts(now)
        const min = parseInt(parts.find(p => p.type === 'minute')!.value)
        const sec = parseInt(parts.find(p => p.type === 'second')!.value)
        return (60 - min) * 60_000 - sec * 1000 - now.getMilliseconds()
    }
    let hourlyInterval: ReturnType<typeof setInterval>
    const timeout = setTimeout(() => {
        fetchData()
        hourlyInterval = setInterval(fetchData, 3_600_000)
    }, msUntilNext())

    return () => {
        clearInterval(pollInterval)
        clearTimeout(timeout)
        clearInterval(hourlyInterval)
    }
}, [])
```

---

## 12. 新页面注册（App.tsx）

```tsx
// 1. 在 App.tsx 中加路由
import YourPage from './pages/YourPage'
<Route path="/your-path" element={<YourPage />} />

// 2. 在 NavRail.tsx 中加导航项
const links = [
    { to: '/',          label: '仪表盘' },
    { to: '/detail',    label: '数据明细' },
    { to: '/your-path', label: '新报表' },
    { to: '/docs',      label: '指标说明' },
]
```
