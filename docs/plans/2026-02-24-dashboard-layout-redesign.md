# 仪表盘布局重构设计方案

**日期**：2026-02-24
**目标**：新增当期平均库龄趋势折线图，重组仪表盘下半区布局，并为超发预警补充发料时间字段。

---

## 一、新增字段：计划发料日期

### 背景
超发预警表格目前无时间维度，无法判断超发事件发生的时间点。
`executeTime`（实际扫码时间）在 NWMS step 2，需逐行请求代价过高。
`ppStartTime`（备料单计划开始时间）已在 step 0 头表中拉取，零额外请求成本。

### 字段流转链路

| 层级 | 字段名 | 说明 |
|------|--------|------|
| NWMS 头表 API | `ppStartTime` | 原始字段，已在爬虫中拉取用于过滤，但未向下传递 |
| `nwms_scraper.py` | `_ppStartTime`（已注入行级） | 爬虫合并头表信息到行级时保留该字段 |
| `issue_audit_report.csv` | `计划发料日期` | build_report.py 写入 CSV 的列名 |
| `IssueAuditSnapshot` | `plan_issue_date` (String 50) | DB 新增列，幂等迁移 |
| `/api/issues/top5` + `/api/issues/list` | `plan_issue_date` | API 返回值新增字段 |
| Dashboard 超发表格 | **计划发料日期** | 第4列，日期格式显示 |

### 不做的事
- 不拉取 `executeTime`（实际扫码时间），代价过高
- `plan_issue_date` 仅展示，不做筛选/排序

---

## 二、仪表盘布局重构

### 当前布局

```
Row 1（3列）: [趋势折线图 col-span-2] | [退料预警卡片列表 col-span-1]
Row 2（3列）: [超发预警全量表格 col-span-3]
```

### 新布局

```
Row 1（2列，各50%）
┌────────────────────────────┬────────────────────────────┐
│ 风险项趋势折线图            │ 当期平均库龄趋势折线图      │
│ 3条线：退料预警总量 /       │ 1条线：avg_aging_hours      │
│ 当期退料预警 / 超发行数     │ 单位：小时，紫色            │
└────────────────────────────┴────────────────────────────┘

Row 2（1/3 + 2/3）
┌──────────────────┬──────────────────────────────────────┐
│ 退料预警全量      │ 进场超发预警全量                     │
│ 卡片列表，滚动    │ 表格8列：物料编号 / 产线 / 关联工单 /│
│                  │ 计划发料日期 / 计划 / 实发 /         │
│                  │ 超发量 / 超发率%(BOM口径)             │
│                  │ 固定表头，纵向滚动 max-h-80           │
└──────────────────┴──────────────────────────────────────┘
```

---

## 三、库龄趋势折线图设计

### 数据来源
- API：`GET /api/kpi/trend` 已返回 `avg_aging_hours` 字段，无需新增接口
- 取最近 14 次批次快照（与风险趋势图一致）

### 趋势图含义说明
风险趋势图保留现有 3 条线，业务含义如下：

| 折线 | 字段 | 含义 |
|------|------|------|
| 退料预警总量 | `alert_group_count` | 完工工单仍有库存（含历史遗留） |
| 当期退料预警 | `confirmed_alert_count` | 同上，排除历史遗留（is_legacy=0） |
| 超发预警行数 | `over_issue_lines` | NWMS 实际发料 > 计划量 |

> **注**：两条退料线的差值 = 历史遗留中完工但未退库的条目。差值持续扩大说明遗留库存未消化。

### ECharts 配置
- 新建独立 `agingChartRef`，不复用风险趋势图实例
- 单折线，紫色（`#a855f7`），smooth，纵轴单位标注"小时"
- 与左侧风险图等高（`h-80`）

---

## 四、变更范围

| 类别 | 文件 | 变更内容 |
|------|------|----------|
| 爬虫 | `src/scrapers/nwms_scraper.py` | 发料行注入 `_ppStartTime` 字段 |
| 分析 | `src/analysis/build_report.py` | issue audit 行写入 `计划发料日期` |
| 模型 | `src/db/models.py` | `IssueAuditSnapshot` 新增 `plan_issue_date` |
| 同步 | `src/db/sync.py` | 写入 `plan_issue_date` |
| 迁移 | `tools/migrate_db.py` | 幂等 ALTER TABLE 新增列 |
| API | `src/api/main.py` | `/api/issues/top5` 和 `/api/issues/list` 返回新字段 |
| 前端 | `frontend/src/pages/Dashboard.tsx` | 布局重构 + 新增库龄折线图 + 超发表格新增列 |

---

## 五、不做的事（YAGNI）

- 不拉取 `executeTime`（实际扫码时间）
- 不对 `plan_issue_date` 做筛选或排序功能
- 不修改 `/api/alerts/top10` 接口（退料预警数据已完整）
- 不修改 DetailPage（明细页已有独立的库龄 Chip 筛选）
- 不新增后端接口（库龄趋势数据已在 trend API 中）
