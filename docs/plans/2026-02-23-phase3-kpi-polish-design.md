# Phase 3 精修：KPI 去偏差化收尾 + 条码追溯

**日期**：2026-02-23
**目标**：修复 Phase 3 KPI 重构后遗留的 9 处不一致问题，补齐条码追溯能力，更新指标说明页。

---

## 一、问题清单

| # | 文件 | 问题 | 类型 |
|---|------|------|------|
| P1 | `Dashboard.tsx` 色带 | 6 色块只有 3 条标注（缺 1-3天/7-14天/14-30天） | 文本缺失 |
| P2 | `main.py /api/alerts/top10` | 仍用 `deviation > 0.01` 过滤 + 按偏差排序 | 逻辑错误 |
| P3 | `Dashboard.tsx` TOP离场 | 标题"偏差组合"，展示偏差值 | 语义错误 |
| P4 | `main.py /api/issues/top5` | 只返回 material_code / over_issue_qty / production_line | 信息不足 |
| P5 | `Dashboard.tsx` TOP进场 | 表格只有 3 列，缺超发率、BOM口径 | 信息不足 |
| P6 | `main.py /api/kpi/trend` | 返回 `high_risk_count`（旧偏差指标），缺 `confirmed_alert_count` | 逻辑错误 |
| P7 | `Dashboard.tsx` 趋势图 | 图例"高风险组数"基于偏差，与新卡片逻辑不符 | 语义错误 |
| P8 | `DetailPage.tsx` | 只有 `barcode_count`（数量），无条码字符串展示 | 功能缺失 |
| P9 | `MetricsDoc.tsx` | 离场审计仍描述偏差/理论余料计算逻辑 | 文档过期 |

---

## 二、变更范围

| 文件 | 变更类型 |
|------|---------|
| `src/db/models.py` | 新增 `AlertReportSnapshot.barcode_list` 字段 |
| `src/analysis/build_report.py` | 聚合时收集条码列表 |
| `src/db/sync.py` | 写入 barcode_list |
| `src/api/main.py` | 修复 top10 / top5 / trend / alerts/list 四个接口 |
| `frontend/src/pages/Dashboard.tsx` | 色带标注、TOP离场、TOP进场、趋势图 |
| `frontend/src/pages/DetailPage.tsx` | AlertTable 新增条码列 |
| `frontend/src/pages/MetricsDoc.tsx` | 离场审计节全面重写，进场审计节保留 |

**不变：** 爬虫逻辑、DataQualitySnapshot、IssueAuditSnapshot 结构、数据库中 deviation/theory_remain 字段（保留备用）

---

## 三、各域设计

### A. 色带标注补全（P1）

色带下方改为 6 个均匀分布标注，与色块一一对应：

| 色块 | 标注文字 |
|------|---------|
| ≤1天（绿） | 健康 |
| 1-3天（浅绿） | 观察中 |
| 3-7天（黄） | 开始关注 |
| 7-14天（橙） | 需跟进 |
| 14-30天（深橙） | 滞留风险 |
| >30天（红） | 严重滞留 |

实现：将现有 `flex justify-between` 的 3-span 改为 6-span，对齐 6 个色块。

---

### B. TOP 离场重设计（P2、P3）

**业务逻辑**：退料预警的首要排序应是"谁最需要操作"——库存量最大的优先。

**API `/api/alerts/top10` 变更：**

```python
# 旧
.where(AlertReportSnapshot.deviation > 0.01)
.order_by(desc(AlertReportSnapshot.deviation))

# 新
COMPLETED = {'Completado', '完成', 'Completed', '已完成', 'Se ha iniciado la construcción'}
.where(AlertReportSnapshot.is_legacy == 0)
.where(AlertReportSnapshot.order_status.in_(COMPLETED))
.order_by(desc(AlertReportSnapshot.actual_inventory))
```

**返回字段：**
```json
{
  "shop_order": "...",
  "material_code": "...",
  "material_desc": "...",
  "warehouse": "...",
  "actual_inventory": 123.0,
  "unit": "PCS",
  "barcode_count": 3,
  "aging_days": 12.5
}
```

**前端 Dashboard 变更：**
- 标题：`退料预警 · 滞留最多 TOP10`
- 每行：工单号 + 物料描述（截断）+ 库存量 + 单位 + 库龄 badge + 线边仓
- 移除偏差 badge，改为 AgingBadge（颜色规则与 DetailPage 一致）

---

### C. TOP 进场重设计（P4、P5）

**业务需求**：超发要看「超发比例」才能判断严重程度，纯超发量无法对比。

**API `/api/issues/top5` 变更，新增返回字段：**
```json
{
  "material_code": "...",
  "production_line": "...",
  "related_wo": "...",
  "demand_qty": 100.0,
  "actual_qty": 192.0,
  "over_issue_qty": 92.0,
  "over_issue_rate": 92.0,
  "bom_demand_qty": 105.6,
  "over_vs_bom_rate": 81.8
}
```

**前端表格列（7列）：**

| 物料编号 | 产线 | 关联工单 | 计划 | 实发 | 超发量 | 超发率% (BOM口径) |

超发率 badge：`> 50%` 红色，`20-50%` 橙色，`< 20%` 黄色。

---

### D. 条码追溯（P8）

**存储方案：** JSON 字符串存于 `AlertReportSnapshot.barcode_list`（Text 字段），不新增子表。

例：`"[\"BC001\",\"BC002\",\"BC003\"]"`

**数据流：**
1. `build_report.py`：聚合 (shop_order, material_code) 时，收集该组所有库存行的「条码」字段
2. `sync.py`：`barcode_list = json.dumps(row.get("barcode_list", []))`
3. `main.py /api/alerts/list`：`"barcode_list": json.loads(r.barcode_list or "[]")`
4. `DetailPage.tsx AlertTable`：新增「条码」列，`barcode_count ≤ 3` 直接展示逗号分隔，`> 3` 展示前 3 条 + `+N更多`（hover 显示全部 tooltip）

**AlertTable 列顺序（更新后）：**

| 工单号 | 物料编号 | 物料描述 | 线边仓 | 实际库存 | 单位 | 库龄 | 条码数 | 条码 |

---

### E. MetricsDoc 重写（P9）

**离场审计节 — 全部重写：**

旧内容（移除）：
- 理论余料 = BOM总需求 − 完工数量 × BOM单件用量
- 偏差 = 实际库存 − 理论余料
- 「高风险」定义（偏差 > 0.01）

新内容：

```
触发条件：2026年工单 + 已完工 + 线边仓仍有库存 = 退料预警
（不依赖偏差计算，偏差受提前合并送料、返工超耗、BOM滞后影响，不可作为操作依据）
```

新增 KPI 卡片说明表：

| 卡片 | 含义 |
|------|------|
| 当期退料预警 | 匹配 2026 工单 + 已完工 + 仍有库存，需立即退料 |
| 工单范围外库存 | 接收时间≥2026 但关联工单不在监控窗口，需人工核查 |
| 历史遗留库存 | 接收时间<2026 或无记录，不纳入预警计算 |
| 当期平均库龄 | 仅统计当期退料预警物料，反映滞留时长 |

新增库龄分布说明：6 色带 + 业务含义。

新增字段说明表（替换旧偏差字段）：

| 指标 | 来源 | 说明 |
|------|------|------|
| 实际库存量 | SSRS 线边仓 | 该（工单，物料）组合的线边仓现存总量 |
| 条码数 | SSRS 线边仓 | 该组合在线边仓的独立批次/条码数量 |
| 库龄 | 分析计算 | 当前时间 − 最早接收时间（天） |

**进场审计节 — 保留现有内容，不变。**

---

### F. 趋势图字段对齐（P6、P7）

**API `/api/kpi/trend` 新增字段：**
```python
"confirmed_alert_count": h.confirmed_alert_count or 0
```

**前端趋势图：**
- 将 `high_risk_count` 系列替换为 `confirmed_alert_count`
- 图例文字：`高风险组数（偏差）` → `当期退料预警`
- 颜色保持红色（#f87171）

---

## 四、不做的事（YAGNI）

- 不删除 `deviation`、`theory_remain`、`high_risk_count` 字段（保留历史数据、导出备用）
- 不新增子表存条码（JSON 字符串足够）
- 不修改爬虫逻辑
- 进场审计 MetricsDoc 节不改动
