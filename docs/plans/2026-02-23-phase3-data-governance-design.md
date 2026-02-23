# 第三阶段设计方案：数据治理

**日期**：2026-02-23
**目标**：解决三系统数据时间窗口不对齐导致的系统性误报，建立数据质量度量基线。

---

## 一、核心问题诊断

| 问题 | 根因 | 影响 |
|------|------|------|
| 线边仓有物料但找不到工单 | IMES 工单拉取窗口太窄（7天），库存中存在历史遗留物料 | 产生大量"假预警"，仓库人员信任度下降 |
| NWMS 备料单关联不上 IMES 工单 | NWMS 全量历史 3600+ 张，IMES 工单只有近期 | 进场超发计算基数有误，match rate 低 |
| 历史遗留物料混入当期预警 | 无时间分层逻辑，所有库存一视同仁参与分析 | 预警列表噪音大，无法区分"真问题"与"历史遗留" |

---

## 二、数据分层规则（线边仓）

线边仓数据**全量保留，不剔除**，按接收时间分两层：

| 分层 | 判断条件 | 处理方式 |
|------|----------|----------|
| **当期数据** | `接收时间 >= 2026-01-01` | 参与核心预警计算，纳入 alert_report |
| **历史遗留** | `接收时间 < 2026-01-01` 或 `接收时间为空` | 保留展示，标记 `is_legacy=True`，不计入 KPI 高风险计数 |

---

## 三、各系统时间窗口对齐策略

### IMES 工单
- **固定起点**：`2026-01-01 00:00:00`（不再动态推算）
- **终点**：同步执行时的当前时间
- **改动位置**：`src/api/scheduler.py` 中 `run_inventory_and_orders()` 的 `--start` 参数

### NWMS 备料单
- **爬虫层（治本）**：`nwms_scraper.py` 新增 `--start` 参数，按 `ppStartTime >= 2026-01-01` 过滤头表，减少无效数据量
- **分析层（兜底）**：`build_report.py` 在进场审计中，仅保留「关联工单存在于当次 IMES 工单集合中」的 NWMS 行，丢弃的行数记录到数据质量报告

### SSRS 库存
- 无时间过滤，全量拉取，由分析层做分层标记

---

## 四、数据质量度量（新增 DB 表）

### 新表：`DataQualitySnapshot`

每次 `run_and_sync()` 执行时写入一条记录：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `batch_id` | String | 对应分析批次 |
| `timestamp` | DateTime | 写入时间 |
| `inventory_total` | Integer | 线边仓总条目数 |
| `inventory_legacy` | Integer | 历史遗留条目数（接收时间<2026 或为空） |
| `inventory_current` | Integer | 当期条目数 |
| `orders_total` | Integer | IMES 工单总数 |
| `alert_matched` | Integer | 当期库存中成功匹配到 IMES 工单的组合数 |
| `alert_unmatched` | Integer | 当期库存中未匹配到工单的组合数（数据质量问题） |
| `alert_match_rate` | Float | `alert_matched / (alert_matched + alert_unmatched) × 100` |
| `nwms_lines_total` | Integer | NWMS 发料行总数（爬虫拉取后） |
| `nwms_lines_matched` | Integer | 关联工单在 IMES 中存在的行数 |
| `nwms_match_rate` | Float | `nwms_lines_matched / nwms_lines_total × 100` |

### `AlertReportSnapshot` 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_legacy` | Boolean | True = 历史遗留（不计入 KPI 高风险） |

---

## 五、`build_report.py` 分析逻辑变更

### 退料预警（离场审计）
```
原逻辑：所有库存条目 → 匹配工单 → 预警
新逻辑：
  ├─ 接收时间 < 2026 或为空 → is_legacy=True，保留但不计入 high_risk_count
  └─ 接收时间 >= 2026      → is_legacy=False，正常参与预警计算
```

### 进场审计（超发预警）
```
原逻辑：所有 NWMS 行 → 计算超发
新逻辑：
  ├─ 关联工单在 IMES 工单集合中 → 正常计算
  └─ 关联不上                   → 记录 nwms_unmatched 计数，不参与超发计算
```

### 返回值扩展
`build_report.run()` 由返回 `(alert_rows, issue_rows)` 改为返回 `(alert_rows, issue_rows, quality_stats)`，`quality_stats` 为字典，供 `sync.py` 写入 `DataQualitySnapshot`。

---

## 六、`sync.py` 变更

`run_and_sync()` 接收 `quality_stats`，在同一 session 中额外写入 `DataQualitySnapshot`。

---

## 七、前端（暂缓）

数据质量指标先落库，待数据稳定后再新增 `/quality` 页面展示匹配率趋势。

---

## 八、不做的事（YAGNI）

- 不修改 SSRS 爬虫（全量拉取保持不变）
- 不回填历史批次的 `is_legacy` 字段（新批次起效即可）
- 不删除历史遗留数据，仅分层标记
- 不新增前端页面（本阶段）
