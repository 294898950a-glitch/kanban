# 墨工厂物料流转审计仪表盘 — 项目交接文档

> **项目阶段**：第八阶段完成（线边仓物料用途状态标签 + Bug 修复 + 睡眠补跑）
> **维护人**：Jay
> **最后更新**：2026-02-26

---

## 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [整体数据流程](#2-整体数据流程)
3. [目录结构](#3-目录结构)
4. [快速启动（Docker）](#4-快速启动docker)
5. [开发模式（裸机）](#5-开发模式裸机)
6. [数据源说明](#6-数据源说明)
7. [爬虫使用说明](#7-爬虫使用说明)
8. [数据清洗与业务逻辑](#8-数据清洗与业务逻辑)
9. [输出文件字段说明](#9-输出文件字段说明)
10. [后端接口清单](#10-后端接口清单)
11. [前端页面说明](#11-前端页面说明)
12. [调度策略](#12-调度策略)
13. [凭据管理](#13-凭据管理)
14. [常见问题](#14-常见问题)
15. [各阶段交付记录](#15-各阶段交付记录)

---

## 1. 项目背景与目标

### 业务背景

灯具制造车间存在以下现场管理痛点：

| 痛点 | 具体表现 |
|------|----------|
| **账实不符** | 系统库存与现场实物不一致，漏扫码或晚报工导致 |
| **退料不及时** | 工单完工后，剩余物料仍堆放在线边仓，未及时退库 |
| **发料不规范** | 实际发料量与标准 BOM 用量偏差大，存在超发或少发 |
| **现场混乱** | 无法快速定位哪些料该退、哪些是死库存 |

### 项目目标

通过数据驱动，建立一套**物料流转预警看板**，实现：

1. **退料预警**：自动识别工单已完成但仍有库存的物料，点名要求退料
2. **发料审计**：对比实际发料量与 BOM 标准用量，发现超发异常
3. **库龄分析**：计算物料在线边仓的停留时长，识别呆滞库存

### 核心预警逻辑（双向审计）

```
退料预警（离场审计）：工单状态 = 已完工  AND  线边仓仍有库存  →  需退料
超发预警（进场审计）：NWMS 实际发料量 > 备料单计划量  →  超发异常
```

> **重要**：偏差（实际库存 - 理论余料）已废弃为触发条件。提前合并送料、返工超耗、BOM 滞后均会导致理论余料失准，直接以「完工+有库存」为触发更可靠。

---

## 2. 整体数据流程

```
┌───────────────────┐  ┌──────────────────────────────┐  ┌───────────────────────────┐
│  SSRS 报表系统     │  │      IMES 业务系统             │  │  NWMS 仓储系统             │
│  10.70.35.26      │  │  10.80.35.11:30088            │  │  10.80.35.11:91           │
│  Windows NTLM     │  │  Bearer Token                 │  │  Bearer Token（独立）      │
└────────┬──────────┘  └──────┬──────────┬─────────────┘  └──────────┬────────────────┘
         │                    │          │                            │
    库存报表接口          工单列表接口  BOM明细接口                  发料单明细接口
         │                    │          │                            │
         ▼                    ▼          ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        Python 爬虫脚本 (src/scrapers/)                              │
│    inventory_scraper.py  shop_order_scraper.py  bom_scraper.py  nwms_scraper.py    │
└─────────────────────────────────┬───────────────────────────────────────────────────┘
                                  │ data/raw/ 原始数据
                                  ▼
                    src/analysis/build_report.py
                       （双向审计引擎）
                                  │
                                  ▼
                        src/db/sync.py
                    （写入 SQLite 快照，带 batch_id）
                                  │
                                  ▼
                       src/api/main.py（FastAPI）
                                  │
                                  ▼
                    frontend/（React + Nginx 反代）
                      http://localhost 仪表盘大屏
```

---

## 3. 目录结构

```
matetial_monitor/
├── README.md                        # 本交接文档
├── docker-compose.yml               # 两服务编排（api + nginx）
├── deploy/
│   ├── Dockerfile                   # API 镜像（python:3.11-slim）
│   └── nginx.conf                   # nginx 反代配置
├── .env.example                     # 凭据模板（IMES/NWMS/SSRS）
├── .gitignore                       # 已排除 .env / data/ / venv/ 等
├── requirements.txt                 # Python 依赖
├── data/
│   └── raw/                         # 爬虫输出 + 分析报告（volume 挂载）
│       ├── inventory_latest.csv
│       ├── shop_orders_latest.{csv,json}
│       ├── bom_details_latest.{csv,json}
│       ├── nwms_issue_heads_latest.{csv,json}
│       ├── nwms_issue_details_latest.{csv,json}
│       ├── alert_report.csv         # 退料预警汇总
│       └── issue_audit_report.csv   # 超发预警报告
├── src/
│   ├── auth/
│   │   └── token_manager.py         # IMES/NWMS Token 自动刷新（HZERO OAuth2）
│   ├── scrapers/
│   │   ├── inventory_scraper.py     # 线边仓库存（SSRS NTLM）
│   │   ├── shop_order_scraper.py    # 工单（IMES API，401自动刷新Token）
│   │   ├── bom_scraper.py           # BOM（IMES API，依赖工单）
│   │   └── nwms_scraper.py          # 发料明细（NWMS API，401自动刷新Token）
│   ├── analysis/
│   │   └── build_report.py          # 双向审计引擎（返回元组供 sync 调用）
│   ├── api/
│   │   ├── main.py                  # FastAPI 应用（9个接口）
│   │   └── scheduler.py             # APScheduler 定时任务（sys.executable 兼容 venv/Docker）
│   └── db/
│       ├── database.py              # SQLAlchemy 引擎配置
│       ├── models.py                # ORM 实体（KPIHistory / AlertReportSnapshot / IssueAuditSnapshot / DataQualitySnapshot）
│       └── sync.py                  # 分析结果写入 SQLite 快照
├── tools/
│   ├── migrate_db.py                # 幂等迁移脚本（新字段 ALTER TABLE）
│   └── test_consistency.py          # 10项端对端一致性校验
├── frontend/
│   ├── Dockerfile                   # Nginx 镜像（multi-stage：node:20 build → nginx:alpine）
│   ├── package.json
│   ├── vite.config.ts               # dev 模式代理 /api → 8000
│   └── src/
│       ├── App.tsx                  # 路由壳（BrowserRouter）
│       ├── components/NavRail.tsx   # 左侧固定导航栏
│       └── pages/
│           ├── Dashboard.tsx        # / 仪表盘
│           ├── DetailPage.tsx       # /detail 数据明细
│           └── MetricsDoc.tsx       # /docs 指标说明
└── docs/
    ├── docker-deploy.txt            # Docker 部署操作手册
    ├── powerbi-dashboard.md         # Power BI 方案（归档，已被 Web 大屏取代）
    └── plans/                       # 各阶段设计文档与实现计划
```

---

## 4. 快速启动（Docker）

**推荐方式，WSL 和服务器均适用。**

### 前置条件

- Docker Engine 已安装
- 能访问内网（10.80.35.11、10.70.35.26）

### 步骤

```bash
# 1. 安装 docker-compose-plugin（首次，需 sudo）
sudo apt install docker-compose-plugin
docker compose version   # 验证

# 2. 创建 .env 并填入凭据
cp .env.example .env
# 编辑 .env，填入：
#   IMES_TOKEN=     （工单/BOM 系统 Bearer Token）
#   NWMS_TOKEN=     （NWMS 仓储系统 Token）
#   SSRS_USERNAME=  （域账号，如 chenweijie）
#   SSRS_PASSWORD=  （域密码）

# 3. 构建并启动
docker compose up -d --build

# 4. 验证
curl http://localhost/api/kpi/summary
# 浏览器访问 http://localhost
```

### 日常运维

```bash
docker compose logs -f api          # 查看后端日志（含爬虫输出）
docker compose ps                   # 查看容器状态
docker compose up -d api            # Token 更新后重建后端容器（restart 不重读 .env）
docker compose up -d --build        # 代码更新后重新构建
docker compose down                 # 停止所有服务
```

### Token 轮换

```bash
# 1. 更新 .env 中对应 Token
# 2. 只重启后端（nginx 不停，零停机）
docker compose restart api
```

### 数据备份

`./data/` 目录直接 bind mount 到宿主机，直接备份即可：
```bash
cp -r ./data ./data_backup_$(date +%Y%m%d)
```

---

## 5. 开发模式（裸机）

适用于本地调试和前端开发。

```bash
# Python 环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 新环境首次运行迁移
python3 tools/migrate_db.py

# 启动后端
PYTHONPATH=. venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 启动前端（另开终端）
cd frontend
pnpm install   # 首次
pnpm run dev
# 访问 http://localhost:5173
```

> **包管理器**：前端使用 `pnpm`，不要用 `npm` 或 `npx pnpm`。

---

## 6. 数据源说明

### 6.1 线边仓库存报表（SSRS）

| 项目 | 值 |
|------|----|
| 系统 | Microsoft SSRS 报表服务器 |
| 地址 | `http://10.70.35.26` |
| 认证 | Windows NTLM（域账号密码） |
| 接口 | `/ReportServer?/imesreport/线边仓库存报表&rs:Format=CSV` |
| 脚本 | `src/scrapers/inventory_scraper.py` |
| 输出 | `data/raw/inventory_latest.csv` |

**关键字段**：

| 字段 | 含义 | 备注 |
|------|------|------|
| **物料** | 物料编号 | 关联 BOM `componentGbo` |
| **现存量** | 该条码当前库存数量 | 按工单+物料汇总后用于分析 |
| **接收时间** | 物料进入线边仓时间 | 用于计算库龄 |
| **指定工单** | 关联生产工单号 | 三表关联核心 Key |
| 条码 | 物料条码 | 每行一个条码 |
| 线边仓 | 所在线边仓编码 | |
| 单位 | 计量单位（PC/M/G等） | |

> 同一工单+物料有多条条码行，分析时需按「工单 + 物料」汇总 `现存量`。

---

### 6.2 工单数据（IMES）

| 项目 | 值 |
|------|----|
| 接口 | `GET http://10.80.35.11:8080/imes-service/v1/0/shopOrder` |
| 认证 | Bearer Token |
| 脚本 | `src/scrapers/shop_order_scraper.py` |
| 输出 | `data/raw/shop_orders_latest.{csv,json}` |

**关键字段**：

| 字段 | 含义 |
|------|------|
| **shopOrder** | 工单号，三表关联 Key |
| **statusDesc** | 工单状态（完工判断依据） |
| **qtyOrdered** | 计划生产数量 |
| **qtyDone** | 实际完工数量 |
| plannedWorkCenterDesc | 产线名称 |

**完工状态集合**：`{'Completado', '完成', 'Completed', '已完成', 'Se ha iniciado la construcción'}`

---

### 6.3 BOM 明细（IMES）

| 项目 | 值 |
|------|----|
| 接口 | `GET .../shopOrder/bom?shopOrder=XXX` |
| 认证 | 同工单（Bearer Token） |
| 脚本 | `src/scrapers/bom_scraper.py` |
| 输出 | `data/raw/bom_details_latest.{csv,json}` |
| 依赖 | 须先运行工单爬虫 |

**关键字段**：

| 字段 | 含义 | 备注 |
|------|------|------|
| **componentGbo** | 组件物料编号 | 对应库存表「物料」字段 |
| **qty** | 单件标准用量 | 每生产1个成品所需数量 |
| **sumQty** | 工单总需求量 | `qty × qtyOrdered` |
| sendQty | 倒冲计算量 | ⚠️ = `qtyDone × qty`，**不是实际发料量** |

---

### 6.4 NWMS 发料明细

| 项目 | 值 |
|------|----|
| 前端 | `http://10.80.35.11:91` |
| API | `http://10.80.35.11:8080/nwms/v1/9/` |
| 认证 | Bearer Token（**独立于 IMES，需单独获取**） |
| siteId | `2.1`（不是 `site=2010`） |
| 脚本 | `src/scrapers/nwms_scraper.py` |
| 输出 | `data/raw/nwms_issue_{heads,details}_latest.{csv,json}` |

**三步接口法**：

```
步骤1: ins_woissue_head?siteId=2.1&page=0&size=200
       → 备料单头表（instructionDocId、workOrderNum、ppStartTime）

步骤2: woissueLineDetail/{instructionDocId}/
       → 发料行（instructionId行级ID、componentCode、demandQuantity、actualQuantity）
       → actualQuantity > demandQuantity 即超发信号

步骤3（可选）: woissueLineActualDetail?instructionId={行级ID}
       → 扫码实发记录（barcode、executeQuantity、executeTime）
```

> **关键**：步骤3 的 `instructionId` 是**行级 ID**（来自步骤2），不是头表的 `instructionDocId`。

---

## 7. 爬虫使用说明

### 7.1 凭据说明

爬虫优先读取环境变量（Docker 注入）。**IMES / NWMS Token 遇到 401 会自动刷新**（无需人工介入）：

| 爬虫 | 环境变量 | 失效处理 |
|------|---------|---------|
| `inventory_scraper.py` | `SSRS_USERNAME` / `SSRS_PASSWORD` | 手动更新 `.env` |
| `shop_order_scraper.py` | `IMES_TOKEN` | **自动刷新**（`src/auth/token_manager.py`） |
| `bom_scraper.py` | `IMES_TOKEN` | 同上 |
| `nwms_scraper.py` | `NWMS_TOKEN` | **自动刷新** |

Token 自动刷新通过 HZERO OAuth2 Implicit Flow 实现，需要 `.env` 中配置：
```
HZERO_USERNAME=   # 工厂系统账号（IMES 和 NWMS 共用）
HZERO_PASSWORD=   # 账号密码
```

### 7.2 单独运行各爬虫

```bash
# 库存（16秒）
python3 src/scrapers/inventory_scraper.py

# 工单（58秒，固定起点 2026-01-01）
python3 src/scrapers/shop_order_scraper.py --start "2026-01-01 00:00:00"

# BOM（约10分钟，需先跑工单）
python3 src/scrapers/bom_scraper.py

# NWMS 发料明细（387秒，增量）
python3 src/scrapers/nwms_scraper.py --start 2026-01-01
```

### 7.3 完整手动更新流程

```bash
cd /home/chenweijie/projects/matetial_monitor

python3 src/scrapers/inventory_scraper.py
python3 src/scrapers/shop_order_scraper.py --start "2026-01-01 00:00:00"
python3 src/scrapers/bom_scraper.py
python3 src/scrapers/nwms_scraper.py --start 2026-01-01

# 生成报告并写入数据库
PYTHONPATH=. python3 -m src.db.sync
```

---

## 8. 数据清洗与业务逻辑

### 8.1 三表关联

```
库存.指定工单  →  工单.shopOrder
库存.物料      →  BOM.componentGbo
```

### 8.2 数据分层规则

| 分层 | 条件 | 说明 |
|------|------|------|
| 当期已核实 | 接收时间 ≥ 2026-01-01，工单在 IMES 监控窗口内，工单已完工 | 退料预警主体 |
| 工单范围外 | 接收时间 ≥ 2026-01-01，工单不在 IMES 窗口 | 不计入预警，仅展示 |
| 历史遗留 | 接收时间 < 2026-01-01 或为空 | 不计入预警，仅展示 |

### 8.3 核心指标计算

**退料预警**（离场审计）：
```
条件：工单状态 = 已完工  AND  实际库存合计 > 0.01  AND  is_legacy = 0
```

**超发预警**（进场审计）：
```
NWMS口径超发量 = actualQuantity - demandQuantity
BOM口径超发量  = actualQuantity - BOM.sumQty（更客观，不受备料员填单影响）
```

**库龄**：
```
库龄（天） = 当前日期 - 接收时间（取日期部分）
```
6档色带：健康(≤1天) / 观察中(1-3天) / 开始关注(3-7天) / 需跟进(7-14天) / 滞留风险(14-30天) / 严重滞留(>30天)

---

## 9. 输出文件字段说明

### alert_report.csv — 退料预警报告

每行代表一个「工单 + 物料」汇总（已按工单+物料去除条码维度重复）。

| 字段 | 来源 | 含义 |
|------|------|------|
| 工单号 | 工单表 | 生产工单编号 |
| 物料编号 | BOM/库存 | 物料编号 |
| 线边仓 | 库存表 | 所在线边仓 |
| 单位 | 库存表 | 计量单位 |
| **实际库存(合计)** | 库存汇总 | 该工单下该物料所有条码现存量之和 |
| 条码数 | 库存表 | 有几个条码 |
| **工单状态** | 工单表 | 此报告中均为完工状态 |
| BOM单件用量 | BOM表 | 每生产1个成品需要的数量 |
| BOM总需求量 | BOM表 | 工单总需求（sumQty） |
| 理论余料 | 计算 | `sumQty - qtyDone × qty` |
| 偏差(实际-理论) | 计算 | 仅供参考，已不作为预警触发条件 |
| 接收时间 | 库存表 | 进入线边仓时间（库龄基准） |
| **is_legacy** | 分析 | 1=历史遗留，0=当期 |
| barcode_list | 分析 | 条码列表（JSON），供条码搜索 |

### issue_audit_report.csv — 超发预警报告

每行代表一条发料行（NWMS 来源）。

| 字段 | 含义 |
|------|------|
| 备料单ID | NWMS instructionDocId |
| 关联工单 | 逗号分隔多工单 |
| **物料编号** | 物料编号 |
| **计划发料量(demandQty)** | NWMS 计划量 |
| **实际发料量(actualQty)** | 仓库实际发出量 |
| **超发量** | `实际 - 计划` |
| 超发率(%) | NWMS 口径 |
| 产线 | 所属产线 |
| **计划发料日期** | NWMS 头表 ppStartTime |
| BOM标准需求量(sumQty) | IMES BOM 工单总需求量 |
| 超发量(vs BOM) | BOM 口径超发量 |
| 超发率%(vs BOM) | BOM 口径超发率 |

---

## 10. 后端接口清单

| 接口 | 用途 |
|------|------|
| `GET /api/kpi/summary` | 最新批次 KPI（5张卡片 + 三层计数） |
| `GET /api/kpi/trend?limit=N` | 最近 N 批次趋势（含 avg_aging_hours） |
| `GET /api/kpi/aging-distribution` | 当期库龄分布（6区间） |
| `GET /api/alerts/top10` | 退料预警全量，按实际库存量排序（无 LIMIT） |
| `GET /api/issues/top5` | 超发全量，含计划日期/BOM口径（无 LIMIT） |
| `GET /api/batches` | 所有历史批次列表 |
| `GET /api/alerts/list?batch_id=&q=` | 离场审计明细（支持工单/物料/条码搜索） |
| `GET /api/issues/list?batch_id=&q=` | 进场审计明细（含计划发料日期） |
| `GET /api/quality/latest` | 最新数据质量快照 |

---

## 11. 前端页面说明

| 路由 | 页面 | 主要功能 |
|------|------|----------|
| `/` | 仪表盘 | 5 KPI 卡片 + 库龄分布色带 + 风险趋势折线图 + 库龄趋势折线图 + 退料预警全量列表（可排序）+ 超发预警全量表格（可排序）；整点自动刷新（对齐蒙特雷时间） |
| `/detail` | 数据明细 | 批次下拉 + 关键字搜索（含条码）+ 库龄 Chip 筛选 + 双 Tab 完整明细；支持 `?aging=` URL 穿透跳转 |
| `/docs` | 指标说明 | 退料预警触发条件 + KPI 卡片定义 + 库龄色带说明 + 进场审计公式 + 数据同步频率 |

---

## 12. 调度策略

调度器随 API 容器启动（APScheduler，`Asia/Shanghai` 时区）。调度器直接 import 爬虫 `run()` 函数调用，无 subprocess，无 PYTHONPATH 问题：

| 任务 | 时间（CST） | 内容 | 耗时 |
|------|------------|------|------|
| 晨间全量 | 06:00 | BOM(IMES) + 库存(SSRS) + 工单(IMES) + NWMS + 分析 + 写DB | ~15 分钟 |
| 4小时同步 | 10 / 14 / 18 / 22 | 库存(SSRS) + 工单(IMES) + NWMS + 分析 + 写DB | ~8 分钟 |

**批次机制**：每次同步生成新 `batch_id`（时间戳），数据追加写入，旧批次保留用于趋势图。每次同步后自动清理 30 天前数据（`purge_old_batches`）。

**睡眠补跑机制**：调度器每次启动时自动检测上次同步时间，若发现有调度节点被跳过（WSL 休眠超过 1 小时），立即异步补跑一次定时同步，日志中以 `[补跑]` 标记。

---

## 13. 凭据管理

### Docker 方式（推荐）

编辑 `.env` 文件，容器通过环境变量读取。Token 更新：编辑 `.env` → `docker compose up -d api`（⚠️ 必须用 `up -d`，`restart` 不重载 `.env`）。

`.env` 字段：
```
IMES_TOKEN=        # 工单/BOM Bearer Token（会自动刷新，初始值填任意有效token即可）
NWMS_TOKEN=        # NWMS Bearer Token（会自动刷新）
SSRS_USERNAME=     # 域账号（如 chenweijie）
SSRS_PASSWORD=     # 域密码
HZERO_USERNAME=    # HZERO 平台账号（用于 Token 自动刷新）
HZERO_PASSWORD=    # HZERO 平台密码
```

### Token 说明

**IMES / NWMS Token（自动管理）**：
- 爬虫遇到 401 时自动调用 `src/auth/token_manager.py` 重新登录获取新 Token
- 新 Token 自动写回 `.env` 和环境变量，无需人工介入
- 前提：`.env` 中 `HZERO_USERNAME` / `HZERO_PASSWORD` 正确

**SSRS**：Windows 域账号密码，密码变更后手动更新 `.env` → `docker compose up -d api`。

---

## 14. 常见问题

**Q: API 返回空数据？**
A: 检查 `.env` Token 是否填写。`docker compose logs api` 查看是否有「失败」日志。

**Q: inventory_scraper 报 401？**
A: NTLM 认证失败，通常密码已修改。更新 `.env` 中 `SSRS_PASSWORD`。

**Q: shop_order_scraper 返回 0 条或 401？**
A: IMES Token 过期，系统会自动刷新。若刷新失败，检查 `.env` 中 `HZERO_USERNAME` / `HZERO_PASSWORD` 是否正确，或账号是否被锁定。

**Q: NWMS Token 过期怎么办？**
A: 同 IMES，系统自动刷新。无需手动操作。

**Q: 大量库存记录未匹配到工单？**
A: 这些库存关联的工单不在 2026-01-01 后的爬取范围内（2025年历史工单）。属正常现象，归为「工单范围外」分层，不计入退料预警。

**Q: plan_issue_date（计划发料日期）显示为空？**
A: 需重新执行 NWMS 爬虫抓取后再触发同步。旧批次快照中此字段为空是正常的。

**Q: 自动刷新时间不准？**
A: 仪表盘刷新对齐墨西哥蒙特雷时间整点（`America/Monterrey`），不是中国时间。

**Q: 服务器上 `docker compose` 命令找不到？**
A: 执行 `sudo apt install docker-compose-plugin` 安装。

---

## 15. 各阶段交付记录

### Phase 1（2026-02-23）— 数据采集与分析

| 类别 | 内容 | 状态 |
|------|------|------|
| 爬虫 | inventory / shop_order / bom / nwms 四个爬虫 | ✅ |
| 分析 | 双向审计报告生成器 `build_report.py` | ✅ |
| 报告 | alert_report.csv + issue_audit_report.csv | ✅ |

### Phase 2（2026-02-23）— Web 全栈大屏

| 类别 | 内容 | 状态 |
|------|------|------|
| 后端 | FastAPI 9个接口 + APScheduler 调度 | ✅ |
| 存储 | SQLite 快照模型 + sync.py | ✅ |
| 前端 | React + Vite + TailwindCSS + ECharts 三页面 | ✅ |

### Phase 3（2026-02-23）— 数据治理 + KPI 重构

| 类别 | 内容 | 状态 |
|------|------|------|
| 数据治理 | 历史遗留分层（is_legacy），数据质量快照表 | ✅ |
| KPI 重构 | 废弃偏差触发，改为「完工+有库存」，三层分类计数 | ✅ |
| 库龄色带 | 6档色带，支持点击穿透跳转明细页 | ✅ |
| BOM 双口径 | 超发量同时输出 NWMS 口径和 BOM 口径 | ✅ |
| 运维工具 | migrate_db.py（幂等）+ test_consistency.py（10项校验） | ✅ |

### Phase 4（2026-02-24）— 仪表盘布局重构

| 类别 | 内容 | 状态 |
|------|------|------|
| 新字段 | plan_issue_date（计划发料日期）全链路：NWMS→爬虫→分析→DB→API→前端 | ✅ |
| 布局 | Row1（50/50）：风险趋势图 + 库龄趋势图；Row2（1/3+2/3，等高）：退料+超发 | ✅ |
| 排序 | 退料预警按库存量/库龄排序；超发表格按数值列排序 | ✅ |
| 自动刷新 | 对齐蒙特雷时间整点（Intl.DateTimeFormat） | ✅ |
| Bug 修复 | scheduler.py 改用 sys.executable（兼容 venv/Docker） | ✅ |

### Phase 5（2026-02-24）— Docker 化

| 类别 | 内容 | 状态 |
|------|------|------|
| deploy/Dockerfile | API 镜像（python:3.11-slim，PYTHONUNBUFFERED + TZ=Asia/Shanghai） | ✅ |
| frontend/Dockerfile | Nginx 镜像（multi-stage node build → nginx） | ✅ |
| deploy/nginx.conf | 反代 /api/ → 127.0.0.1:8000，React Router try_files | ✅ |
| docker-compose.yml | 两服务（host 网络 + bind mount + env_file + TZ env） | ✅ |
| .env.example | 四个凭据字段模板 | ✅ |
| 爬虫 env 支持 | 三个爬虫读取环境变量（硬编码回退） | ✅ |
| 运维文档 | docs/docker-deploy.txt（完整部署操作手册） | ✅ |

### Phase 6（2026-02-24）— Token 自动刷新 + 调度器重构

| 类别 | 内容 | 状态 |
|------|------|------|
| src/auth/token_manager.py | HZERO OAuth2 Implicit Flow 自动登录，RSA 加密密码 | ✅ |
| shop_order_scraper.py | 401 触发自动刷新 IMES Token，写回 .env，重试请求 | ✅ |
| nwms_scraper.py | 401 触发自动刷新 NWMS Token，写回 .env，重试请求 | ✅ |
| .env | 新增 HZERO_USERNAME / HZERO_PASSWORD 凭据 | ✅ |
| scheduler.py | 改用直接 import 调用爬虫 run()，彻底消除 PYTHONPATH 问题 | ✅ |
| bom_scraper.py | 内部引用改为绝对包路径（from src.scrapers.xxx） | ✅ |

### Phase 7（2026-02-25）— 通用物料剔除 Toggle + 调度优化

| 类别 | 内容 | 状态 |
|------|------|------|
| src/config/common_materials.py | 通用物料白名单（8 个物料编号），集中管理 | ✅ |
| kpi_history 模型/DB | 新增 confirmed_alert_count_excl / avg_aging_hours_excl 列，同步时预算 | ✅ |
| build_report.py | 剔除白名单后计算退料预警数和平均库龄，写入 quality_stats | ✅ |
| sync.py | 持久化两个剔除后字段；每次同步后自动清理 30 天前数据 | ✅ |
| main.py | 5 个离场接口支持 exclude_common 参数（summary/trend/aging-distribution/top10/list） | ✅ |
| Dashboard.tsx | 离场审计区域加 Toggle，联动 KPI / 列表 / 趋势图 / 库龄分布 | ✅ |
| DetailPage.tsx | 离场 Tab 加独立 Toggle，进场审计不受影响 | ✅ |
| scheduler.py | 调度改为 06/10/14/18/22 CST（每天 5 次），06:00 晨间含 BOM 全量 | ✅ |
| MetricsDoc.tsx | 补充通用物料 Toggle 说明、更新同步频率展示 | ✅ |

### Phase 8（2026-02-25）— 线边仓物料用途状态标签

| 类别 | 内容 | 状态 |
|------|------|------|
| src/db/models.py | 新增 InventoryStatusSnapshot 表（全量库存快照）；AlertReportSnapshot 新增 reuse_label 列 | ✅ |
| tools/migrate_db.py | 幂等迁移：新增 reuse_label 列 + inventory_status_snapshots 表 | ✅ |
| src/analysis/build_report.py | 新增 build_inventory_status()；提取 _build_reuse_sets / _calc_reuse_label helper；COMPLETED_STATUSES 修正（移除在制状态） | ✅ |
| src/db/sync.py | 同步全量库存状态至新表；退料预警行写入 reuse_label；purge 覆盖新表 | ✅ |
| src/api/main.py | 新增 /api/inventory/status 接口（支持 label / exclude_common 过滤）；统一 calculate_aging_days 模块级函数；alerts/top10 + alerts/list 返回 reuse_label | ✅ |
| frontend/src/components/WoStatusChip.tsx | 新增独立 WoStatusChip 组件（5 种状态彩色 Chip） | ✅ |
| Dashboard.tsx | 退料预警列表新增「物料状态」列，展示 reuse_label 徽标 | ✅ |
| DetailPage.tsx | 离场审计 Tab 切换为全量库存数据源；新增 6 类状态筛选 Chip | ✅ |
| MetricsDoc.tsx | 新增物料用途状态说明（5 种标签含义及操作建议） | ✅ |

### Phase 8 Bug 修复 + 补跑机制（2026-02-26）

| 类别 | 内容 | 状态 |
|------|------|------|
| WoStatusChip.tsx | 新增 isLegacy prop；空标签时显示「📦 历史遗留」或「❓ 工单外」兜底 Chip（原为空白） | ✅ |
| DetailPage.tsx | 「已完工待退」筛选 Chip 排除 reuse_label 行，修复混入复用条目的问题 | ✅ |
| scheduler.py | 新增 check_and_catchup()：启动时检测跳过的调度节点，异步补跑；解决 WSL 休眠导致同步丢失 | ✅ |
| ~/.bashrc | 新增 TZ=America/Monterrey，git 提交时间显示墨西哥时区（-0600） | ✅ |
