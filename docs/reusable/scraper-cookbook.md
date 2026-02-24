# 爬虫模式手册（Scraper Cookbook）

> 本文档提取自 LMT-Kanban 项目，供新报表爬虫快速复用。
> 所有爬虫均在 `src/scrapers/` 下，Python 3.11，依赖见 `requirements.txt`。

---

## 1. 项目级约定

```python
# 输出目录统一写这里
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

# 保存最新快照（固定文件名）+ 带时间戳归档
ts = datetime.now().strftime("%Y%m%d_%H%M")
save_json(rows, f"xxx_{ts}.json")
save_json(rows, "xxx_latest.json")   # 供分析层读取
save_csv(rows,  f"xxx_{ts}.csv")
save_csv(rows,  "xxx_latest.csv")
```

---

## 2. HZERO Bearer Token 认证（IMES / NWMS）

### 2.1 手动获取（浏览器 F12）

```
IMES:  http://10.80.35.11:30088  → F12 → Network → 任意请求 → Authorization: Bearer <token>
NWMS:  http://10.80.35.11:91    → 同上
```

### 2.2 自动刷新（推荐，已内置）

Token 过期（401）时自动登录 HZERO 获取新 Token，无需人工介入：

```python
from src.auth.token_manager import refresh_imes_token, refresh_nwms_token

# 在 fetch 函数中加 401 重试：
resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
if resp.status_code == 401:
    new_token = refresh_imes_token()   # 或 refresh_nwms_token()
    HEADERS = _make_headers(new_token)
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
resp.raise_for_status()
```

`token_manager.py` 实现原理：HZERO OAuth2 Implicit Flow
1. POST `/oauth/login`（RSA 加密密码）
2. GET `/oauth/oauth/authorize?response_type=token&client_id=XXX&redirect_uri=XXX`
3. 从 Location 响应头 fragment 取 `access_token`
4. 写回 `.env` + `os.environ`

---

## 3. IMES API 通用请求头

```python
def _make_headers(token: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": f"Bearer {token}",
        "menu": "",
        "system": "IMES",
        "origin": "http://10.80.35.11:30088",
        "referer": "http://10.80.35.11:30088/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

# Token 优先读环境变量（Docker 注入），回退到 .env 硬编码
token = os.environ.get("IMES_TOKEN", "")
```

---

## 4. 分页拉取模式（IMES 标准）

响应结构：`{"success": true, "rows": {"content": [...], "totalElements": N}}`

```python
def fetch_all(start_date: str) -> list[dict]:
    all_rows, page = [], 0
    while True:
        params = {
            "signTime": int(time.time() * 1000),   # 必填，防缓存
            "page": page,
            "size": 100,
            "site": "2010",
            "language": "zh_CN",
            # ...其他业务参数
        }
        data = fetch_page(page, params)
        content = data.get("rows", {}).get("content", [])
        if not content:
            break
        all_rows.extend(content)
        total = data.get("rows", {}).get("totalElements", 0)
        if len(all_rows) >= total or len(content) < 100:
            break
        page += 1
        time.sleep(0.3)   # 礼貌性延迟
    return all_rows
```

---

## 5. NWMS 三步发料接口

```
Base: http://10.80.35.11:8080/nwms/v1/9/
siteId 参数: 2.1（注意：不是 site=2010）
```

```python
# 步骤1：备料单头表（含计划发料日期 ppStartTime）
GET ins_woissue_head?siteId=2.1&page=0&size=200
→ 返回 instructionDocId, demandListNumber, workOrderNum, ppStartTime, productionLine

# 步骤2：发料行明细（超发判断）
GET woissueLineDetail/{instructionDocId}/
→ 返回 instructionId（行级ID）, componentCode, demandQuantity, actualQuantity
→ actualQuantity > demandQuantity 即超发

# 步骤3（可选）：扫码实发追溯
GET woissueLineActualDetail?instructionId={行级ID}   # ⚠️ 行级ID，不是头表ID
→ 返回 barcode, executeQuantity, executeTime, fromWarehouse
```

### NWMS 请求头

```python
def _make_nwms_headers(token: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"bearer {token}",   # 注意：小写 bearer
        "origin": "http://10.80.35.11:91",
        "referer": "http://10.80.35.11:91/",
        "user-agent": "Mozilla/5.0 ...",
    }

token = os.environ.get("NWMS_TOKEN", "")
```

---

## 6. SSRS 库存报表（Windows NTLM）

```python
import requests
from requests_ntlm import HttpNtlmAuth

SSRS_BASE = "http://10.70.35.26"
REPORT_PATH = "/ReportServer?/imesreport/线边仓库存报表&rs:Format=CSV"

username = os.environ.get("SSRS_USERNAME", "chenweijie")
password = os.environ.get("SSRS_PASSWORD", "")

resp = requests.get(
    f"{SSRS_BASE}{REPORT_PATH}",
    auth=HttpNtlmAuth(username, password),
    timeout=60,
)
resp.raise_for_status()
# 直接是 CSV 文本，按行解析即可
```

---

## 7. 数据保存模板

```python
import json, csv
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

def save_json(rows: list[dict], filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return path

def save_csv(rows: list[dict], filename: str) -> Path:
    if not rows:
        return None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel 能直接打开
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path
```

---

## 8. 调度器注册新爬虫（scheduler.py）

```python
# 整点任务 — 加入新爬虫脚本
HOURLY_SCRIPTS = [
    ("inventory",   ["python3", "src/scrapers/inventory_scraper.py"]),
    ("shop_order",  ["python3", "src/scrapers/shop_order_scraper.py", "--start", "2026-01-01 00:00:00"]),
    ("nwms",        ["python3", "src/scrapers/nwms_scraper.py", "--start", "2026-01-01"]),
    ("your_new",    ["python3", "src/scrapers/your_new_scraper.py"]),  # 新增这行
]
```

---

## 9. 内网系统地址速查

| 系统 | 前端 | API Base | 认证 |
|------|------|----------|------|
| IMES | `http://10.80.35.11:30088` | `http://10.80.35.11:8080/imes-service/v1/0/` | Bearer Token（自动刷新） |
| NWMS | `http://10.80.35.11:91` | `http://10.80.35.11:8080/nwms/v1/9/` | Bearer Token（自动刷新） |
| SSRS | — | `http://10.70.35.26` | Windows NTLM |
