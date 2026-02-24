# 通用物料剔除 Toggle 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在离场审计中增加「含通用物料 ⇌ 已剔除通用物料」Toggle，KPI 卡片、预警列表、趋势图同步切换，进场审计不受影响。

**Architecture:** 白名单存配置文件；分析引擎同步时预算剔除后的数字写入 DB；API 层接收 `exclude_common` 参数决定返回哪列数据；前端 Toggle 仅改 API 请求参数，不增加新页面。

**Tech Stack:** Python 3.11 / SQLite / SQLAlchemy / FastAPI / React + TypeScript / axios

---

## Task 1: 创建通用物料白名单配置文件

**Files:**
- Create: `src/config/__init__.py`
- Create: `src/config/common_materials.py`

**Step 1: 创建 `src/config/__init__.py`（空文件）**

**Step 2: 创建 `src/config/common_materials.py`**

```python
COMMON_MATERIALS = {
    "1000253006",
    "1000122998",
    "1000179092",
    "1000017041",
    "1000243256",
    "1000223210",
}
```

**Step 3: Commit**

```bash
git add src/config/
git commit -m "feat: add common materials whitelist config"
```

---

## Task 2: DB 迁移 — kpi_history 加新列

**Files:**
- Modify: `tools/migrate_db.py`
- Modify: `src/db/models.py`

**Step 1: 在 `tools/migrate_db.py` 末尾参考现有 ALTER TABLE 模式，追加新列迁移**

找到文件末尾的 `kpi_history` 迁移块（约第 67-79 行），在其后追加：

```python
# 通用物料剔除计数列
try:
    cursor.execute("ALTER TABLE kpi_history ADD COLUMN confirmed_alert_count_excl INTEGER DEFAULT 0;")
    print("[MIGRATE] ✅ kpi_history.confirmed_alert_count_excl 列新增成功")
except Exception:
    print("[MIGRATE] ℹ️  kpi_history.confirmed_alert_count_excl 列已存在，跳过")
conn.commit()
```

**Step 2: 运行迁移**

```bash
PYTHONPATH=. python3 tools/migrate_db.py
```

期望输出：`[MIGRATE] ✅ kpi_history.confirmed_alert_count_excl 列新增成功`

**Step 3: 在 `src/db/models.py` 的 `KPIHistory` 类中，在 `legacy_count` 那行后追加新列定义**

```python
confirmed_alert_count_excl = Column(Integer, default=0)  # 剔除通用物料后的退料预警数
```

**Step 4: Commit**

```bash
git add tools/migrate_db.py src/db/models.py
git commit -m "feat: add confirmed_alert_count_excl column to kpi_history"
```

---

## Task 3: 分析引擎 — 同步时预算剔除后数量

**Files:**
- Modify: `src/analysis/build_report.py:507-523`（quality_stats 构建块）

**Step 1: 在 `build_report.py` 顶部 import 区加入**

```python
from src.config.common_materials import COMMON_MATERIALS
```

**Step 2: 找到 `confirmed_alerts` 列表定义（约 456 行），在它下方加一行**

```python
confirmed_alerts_excl = [
    r for r in confirmed_alerts
    if r.get("物料编号", "") not in COMMON_MATERIALS
]
```

**Step 3: 在 `quality_stats` dict（约 507 行）中，`confirmed_alert_count` 行之后加一行**

```python
"confirmed_alert_count_excl": len(confirmed_alerts_excl),
```

**Step 4: Commit**

```bash
git add src/analysis/build_report.py
git commit -m "feat: calculate confirmed_alert_count_excl in analysis engine"
```

---

## Task 4: 同步层 — 写入新列到 DB

**Files:**
- Modify: `src/db/sync.py:39-55`（KPIHistory 构建块）

**Step 1: 找到 `KPIHistory(...)` 构造（约 40 行），在 `legacy_count=...` 行后加一行**

```python
confirmed_alert_count_excl=quality_stats.get("confirmed_alert_count_excl", 0),
```

**Step 2: Commit**

```bash
git add src/db/sync.py
git commit -m "feat: persist confirmed_alert_count_excl to kpi_history"
```

---

## Task 5: API — 4 个接口加 exclude_common 参数

**Files:**
- Modify: `src/api/main.py`

**Step 1: 在 `main.py` 顶部 import 区加入**

```python
from src.config.common_materials import COMMON_MATERIALS
```

**Step 2: 修改 `GET /api/kpi/summary`（约第 34 行）**

函数签名改为：
```python
def get_kpi_summary(exclude_common: bool = False):
```

return dict 中，`confirmed_alert_count` 那行改为：
```python
"confirmed_alert_count": (latest_kpi.confirmed_alert_count_excl or 0)
    if exclude_common else (latest_kpi.confirmed_alert_count or 0),
```

**Step 3: 修改 `GET /api/kpi/trend`（约第 61 行）**

函数签名改为：
```python
def get_kpi_trend(limit: int = 14, exclude_common: bool = False):
```

列表推导中 `confirmed_alert_count` 那行改为：
```python
"confirmed_alert_count": (h.confirmed_alert_count_excl or 0)
    if exclude_common else (h.confirmed_alert_count or 0),
```

**Step 4: 修改 `GET /api/alerts/top10`（约第 131 行）**

函数签名改为：
```python
def get_alerts_top10(exclude_common: bool = False):
```

在 `.where(AlertReportSnapshot.order_status.in_(COMPLETED_STATUSES))` 行后加：
```python
if exclude_common:
    stmt = stmt.where(AlertReportSnapshot.material_code.not_in(list(COMMON_MATERIALS)))
```

注意：这里需要把现有的链式 `.where()` 拆成先构建 `stmt` 再追加条件的写法。参考 `alerts/list` 接口的 stmt 模式。

**Step 5: 修改 `GET /api/alerts/list`（约第 228 行）**

函数签名改为：
```python
def get_alerts_list(batch_id: str = "", q: str = "", exclude_common: bool = False):
```

在现有 `if q:` 块之后加：
```python
if exclude_common:
    stmt = stmt.where(AlertReportSnapshot.material_code.not_in(list(COMMON_MATERIALS)))
```

**Step 6: 手动测试 4 个接口**

```bash
# 需先确保后端跑着（Docker 或裸机）
curl "http://localhost:8000/api/kpi/summary?exclude_common=true"
curl "http://localhost:8000/api/kpi/trend?exclude_common=true"
curl "http://localhost:8000/api/alerts/top10?exclude_common=true"
curl "http://localhost:8000/api/alerts/list?exclude_common=true" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'rows')"
```

期望：`confirmed_alert_count` 数值比不加参数时小（或相等，若无通用物料行）

**Step 7: Commit**

```bash
git add src/api/main.py
git commit -m "feat: add exclude_common param to 4 alert API endpoints"
```

---

## Task 6: 前端 Dashboard — 离场审计区域加 Toggle

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: 在 useState 区域加新状态（找到其他 useState 行附近）**

```tsx
const [excludeCommon, setExcludeCommon] = useState(false)
```

**Step 2: 修改 `fetchData` 里的 3 个 axios 请求，传入参数**

```tsx
axios.get<KPISummary>('/api/kpi/summary', { params: { exclude_common: excludeCommon } }),
axios.get<AlertTop[]>('/api/alerts/top10', { params: { exclude_common: excludeCommon } }),
axios.get<KPITrend[]>('/api/kpi/trend', { params: { exclude_common: excludeCommon } }),
```

**Step 3: 让 `fetchData` 在 `excludeCommon` 变化时重新触发**

找到现有的 `useEffect(() => { fetchData() }, [...])` 依赖数组，加入 `excludeCommon`

**Step 4: 在离场审计区域标题旁加 Toggle 组件**

找到仪表盘中「退料预警」/「离场审计」的 section 标题（h2 或类似元素），在其右侧加：

```tsx
<button
  onClick={() => setExcludeCommon(v => !v)}
  className={`text-xs px-3 py-1 rounded-full border transition-colors ${
    excludeCommon
      ? 'bg-yellow-600 border-yellow-500 text-white'
      : 'bg-gray-700 border-gray-600 text-gray-300 hover:border-gray-400'
  }`}
>
  {excludeCommon ? '已剔除通用物料' : '含通用物料'}
</button>
```

**Step 5: 确认趋势图使用的数据源是 `kpi/trend` 响应（已在 Step 2 加了参数），无需额外修改趋势图组件**

**Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add exclude_common toggle to Dashboard 离场审计 section"
```

---

## Task 7: 前端 DetailPage — 离场 Tab 加独立 Toggle

**Files:**
- Modify: `frontend/src/pages/DetailPage.tsx`

**Step 1: 在 useState 区域加新状态**

```tsx
const [excludeCommon, setExcludeCommon] = useState(false)
```

**Step 2: 找到 `/api/alerts/list` 的 axios 请求，加入参数**

```tsx
axios.get<AlertRow[]>('/api/alerts/list', {
  params: { ...params, exclude_common: excludeCommon }
})
```

**Step 3: 在 `useEffect` 依赖数组中加入 `excludeCommon`**

**Step 4: 在离场 Tab 标题旁加同款 Toggle 按钮（复用 Task 6 Step 4 的样式）**

**Step 5: Commit**

```bash
git add frontend/src/pages/DetailPage.tsx
git commit -m "feat: add independent exclude_common toggle to DetailPage 离场Tab"
```

---

## Task 8: 重建容器并验证

**Step 1: 重建前端 + API 容器**

```bash
cd /home/chenweijie/projects/matetial_monitor
docker compose build nginx && docker compose up -d
```

**Step 2: 验证 Toggle 功能**

- 仪表盘：点 Toggle，当期退料预警数字变化，趋势图重绘
- 明细页离场 Tab：点 Toggle，表格行数变化，通用物料行消失

**Step 3: 验证进场审计不受影响**

- 切换仪表盘 Toggle，超发预警数字不变
- 明细页进场 Tab 不显示 Toggle

**Step 4: 最终 Commit（若有遗漏小修）**

```bash
git add -A
git commit -m "fix: post-integration tweaks for common material toggle"
```
