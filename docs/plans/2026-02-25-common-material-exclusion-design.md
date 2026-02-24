# 通用物料剔除 — 设计文档

**日期：** 2026-02-25
**背景：** 部分物料（如辅料、共用件）会跨工单共享，在线边仓长期滞留属正常，不应触发退料预警。需在保留原口径的基础上，提供剔除通用物料的第二视角。

---

## 范围

仅影响**离场审计**（退料预警）。进场审计、历史遗留、工单范围外 KPI 不受影响。

---

## 通用物料白名单

存放于 `src/config/common_materials.py`，后续新增/删除直接编辑此文件。

当前清单（6 个）：
- 1000253006
- 1000122998
- 1000179092
- 1000017041
- 1000243256
- 1000223210

---

## 后端改动

### 1. 配置文件
新增 `src/config/common_materials.py`，存放白名单 Set。

### 2. 分析引擎（build_report.py）
每次同步时，额外计算剔除通用物料后的退料预警数，写入 `kpi_history` 表新列 `confirmed_alert_count_excl_common`。趋势图查询时直接读此字段，无需运行时重算。

### 3. API 接口（main.py）
以下 4 个接口新增可选参数 `exclude_common: bool = False`，默认 false，不影响现有行为：

| 接口 | exclude_common=true 时的行为 |
|------|---------------------------|
| `GET /api/kpi/summary` | 当期退料预警数从快照重算，过滤白名单物料 |
| `GET /api/kpi/trend` | 读 `confirmed_alert_count_excl_common` 字段 |
| `GET /api/alerts/top10` | 过滤白名单物料行 |
| `GET /api/alerts/list` | 过滤白名单物料行 |

---

## 前端改动

### Toggle 位置
- **仪表盘**：离场审计区域标题旁
- **明细页离场 Tab**：Tab 标题旁
- 两处状态**独立**，不互相联动

### Toggle 文案
- 默认状态：`含通用物料`
- 切换后：`已剔除通用物料`
- 切换时显示 loading 状态，避免数字闪跳

### 影响范围

| 区域 | 受影响 |
|------|--------|
| 当期退料预警 KPI 卡片 | ✅ |
| 退料预警全量列表（仪表盘） | ✅ |
| 趋势图（退料预警走势） | ✅ |
| 明细页离场 Tab 表格 | ✅（独立 Toggle）|
| 历史遗留 / 工单范围外 KPI | ❌ |
| 进场审计（所有区域） | ❌ |

---

## 改动文件清单

| 文件 | 类型 |
|------|------|
| `src/config/common_materials.py` | 新增 |
| `src/analysis/build_report.py` | 修改（新增预算列） |
| `tools/migrate_db.py` | 修改（kpi_history 加列） |
| `src/api/main.py` | 修改（4 个接口加参数） |
| `frontend/src/pages/Dashboard.tsx` | 修改（Toggle + API 参数）|
| `frontend/src/pages/DetailPage.tsx` | 修改（Toggle + API 参数）|
