# Phase 5 Docker 化设计文档

**目标：** 将后端 API + 前端静态页 打包为两个 Docker 容器，通过 docker-compose 统一编排，支持本地 WSL 开发与远端服务器生产部署。

**日期：** 2026-02-24

---

## 设计决策汇总

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 部署目标 | WSL 本地 + 远端服务器 | 开发验证 + 生产运行 |
| Token 管理 | `.env` 文件，容器读环境变量 | 无需重建镜像，token 轮换只需改文件 |
| 前端服务 | Nginx 容器 | 分离清晰，nginx 同时反代 `/api/*` |
| 前端构建 | Multi-stage Dockerfile | 服务器无需装 node/pnpm，一条命令构建 |
| 数据持久化 | Host bind mount `./data:/app/data` | 宿主机直接查文件，备份简单 |
| 编排工具 | docker-compose v2 (`docker compose`) | 需先安装 `docker-compose-plugin` |
| 网络模式 | `network_mode: host` | 容器需访问内网 IP（10.80.35.11、10.70.35.26） |
| 重启策略 | `restart: unless-stopped` | 异常自动恢复，手动 stop 不自动起 |
| 服务器部署 | `git pull + docker compose build` | 最简单，服务器直接拉代码库 |

---

## 架构概览

```
┌─────────────────── docker-compose.yml ───────────────────┐
│                                                           │
│  ┌─────────────┐        ┌──────────────────────────┐     │
│  │   nginx     │ :80    │         api              │     │
│  │  (frontend) │──/api/*│  FastAPI + APScheduler   │     │
│  │  静态文件    │──proxy→│  port 8000               │     │
│  └─────────────┘        └──────────┬───────────────┘     │
│                                    │ bind mount           │
│                               ./data:/app/data            │
│                          (SQLite DB + raw CSV)            │
│                                                           │
│  .env  →  IMES_TOKEN / NWMS_TOKEN / 其他敏感配置          │
│                                                           │
│  network_mode: host（两个服务共用宿主机网络栈）             │
└───────────────────────────────────────────────────────────┘
```

**两个服务：**
- `api`：现有 `Dockerfile`（python:3.11-slim），含 APScheduler 定时任务，读 `.env` 获取 token
- `nginx`：新建 `frontend/Dockerfile`，multi-stage（node:20 build → nginx:alpine serve），反代 `/api/*` → `127.0.0.1:8000`

**host 网络说明：** 已通过测试验证（`--network host`），容器可访问 IMES（10.80.35.11:8080）和 SSRS（10.70.35.26）。两容器通信走 `localhost:8000`，无需自定义 bridge 网络。

---

## 新增文件清单

```
matetial_monitor/
├── Dockerfile              # 已有，无需改动
├── frontend/Dockerfile     # 新建：multi-stage node build → nginx serve
├── nginx.conf              # 新建：nginx 反代配置（/api/* → 127.0.0.1:8000）
├── docker-compose.yml      # 新建：两服务编排
├── .env                    # 新建：敏感配置（不入 git）
├── .env.example            # 新建：模板文件（入 git，值留空）
└── .gitignore              # 补充：添加 .env
```

**不需要改动的文件：**
- `src/` 所有 Python 代码
- `frontend/src/` 所有 React 代码
- `requirements.txt`

---

## 运维流程

### 首次启动（WSL 本地）
```
1. cp .env.example .env        # 填入 IMES_TOKEN、NWMS_TOKEN
2. docker compose up -d --build
3. 浏览器访问 http://localhost
```

### 首次部署（远端服务器）
```
1. git clone <repo> && cd matetial_monitor
2. apt install docker-compose-plugin  # 如未安装
3. cp .env.example .env               # 填入 token
4. docker compose up -d --build
```

### 代码更新
```
git pull && docker compose up -d --build
```

### Token 过期轮换
```
# 编辑 .env，更新 IMES_TOKEN 或 NWMS_TOKEN
docker compose restart api    # 只重启后端，nginx 不停，零停机
```

### 日常运维命令
```
docker compose logs -f api     # 查看后端日志（含爬虫输出）
docker compose ps              # 查看容器状态
docker compose down            # 停止所有服务
```

### 数据备份
直接备份宿主机 `./data/` 目录（bind mount，无需进入容器）。

---

## .env.example 模板字段

```
IMES_TOKEN=
NWMS_TOKEN=
# 可扩展：SCRAPER_TIMEOUT、LOG_LEVEL 等
```

---

## 前置条件

| 环境 | 需要安装 |
|------|---------|
| WSL / 服务器 | Docker Engine（已有）、`docker-compose-plugin`（需安装） |
| 宿主机 | 无需 node、python、pnpm |

安装命令（Ubuntu/Debian）：
```
apt install docker-compose-plugin
```

---

## 实施计划（参考）

1. 安装 `docker-compose-plugin`
2. 新建 `frontend/Dockerfile`（multi-stage）
3. 新建 `nginx.conf`
4. 新建 `docker-compose.yml`
5. 新建 `.env.example` + 补充 `.gitignore`
6. 本地 `docker compose up -d --build` 验证
7. 服务器 `git clone + docker compose up` 验证
