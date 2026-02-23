# Power BI 看板方案说明

> **状态**：归档参考文档。本方案已被 Phase 2 引入的 Web 全栈大屏取代，Power BI 相关草图文件已移至 `archive/` 目录。
> 如需重新启用 Power BI，可参照本文档接入已有的 CSV 分析输出文件。

---

## 1. 数据接入方式

将以下文件导入 Power BI（建议使用**文件夹连接**方式，刷新时自动读取 latest 文件）：

| 表名（Power BI 中） | 文件 | 用途 |
|---------------------|------|------|
| Inventory | `data/raw/inventory_latest.csv` | 事实表：当前库存快照 |
| ShopOrders | `data/raw/shop_orders_latest.csv` | 维度表：工单信息 |
| BomDetails | `data/raw/bom_details_latest.csv` | 事实表：BOM用量与发料 |
| NwmsIssueDetails | `data/raw/nwms_issue_details_latest.csv` | 事实表：NWMS发料行（含actualQuantity） |
| AlertReport | `data/raw/alert_report.csv` | 分析结果：退料预警（离场审计） |
| IssueAuditReport | `data/raw/issue_audit_report.csv` | 分析结果：超发预警（进场审计） |

---

## 2. 表关系（数据模型）

```
ShopOrders  [shopOrder]     ──1:N──  BomDetails [shopOrder]
ShopOrders  [shopOrder]     ──1:N──  Inventory  [指定工单]
BomDetails  [componentGbo]  ──N:1──  Inventory  [物料]
```

---

## 3. 核心 DAX 度量值

```dax
// 退料预警组数
退料预警组数 =
COUNTROWS(
    FILTER(AlertReport, AlertReport[偏差(实际-理论)] > 0.01)
)

// 平均库龄（小时）
平均库龄_小时 =
AVERAGEX(
    Inventory,
    DATEDIFF(Inventory[接收时间], NOW(), HOUR)
)

// 超48小时库存占比
超期库存占比 =
DIVIDE(
    COUNTROWS(FILTER(Inventory,
        DATEDIFF(Inventory[接收时间], NOW(), HOUR) > 48
    )),
    COUNTROWS(Inventory)
)

// 超发发料行数
超发行数 =
COUNTROWS(
    FILTER(IssueAuditReport, IssueAuditReport[超发量] > 0.01)
)

// 超发率（进场审计）
发料偏差率 =
DIVIDE(
    SUM(IssueAuditReport[超发量]),
    SUM(IssueAuditReport[计划发料量(demandQty)])
)
```

---

## 4. 建议看板页面结构

**Page 1 — 总览（Overview）**
- KPI 卡片：退料预警组数 / 超期(>48h)库存条数 / 今日工单完成率
- 条形图：各产线退料预警数量排名
- 表格：退料预警清单（工单号 / 物料 / 线边仓 / 实际库存 / 超期天数）

**Page 2 — 发料审计（Issuing Audit）**
- 散点图：各工单发料偏差率（X轴=工单，Y轴=偏差%，超过±5%标红）
- 矩阵表：工单 × 物料 的发料偏差详情
- 切片器：按产线、日期筛选

**Page 3 — 库龄分析（Inventory Aging）**
- 散点图：X轴=接收时间，Y轴=现存量，颜色=库龄分段（绿/黄/红）
- 直方图：库龄分布（0-24h / 24-48h / 48-72h / >72h）
- 表格：>72小时钉子户物料清单，按库龄降序排列

**Page 4 — 工单齐套（Kitting Status）**（待开发）
- 矩阵表：行=在制工单，列=关键物料类别
- 颜色：绿=已足量到位，黄=部分到位，红=缺料
