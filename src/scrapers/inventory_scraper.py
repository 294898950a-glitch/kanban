"""
线边仓库存报表爬虫 - Microsoft SSRS 报表系统
服务器：http://10.70.35.26
认证方式：Windows NTLM（域账号密码）
原理：通过 SSRS ReportServer 直接导出 CSV，绕过复杂的 WebForms 交互
"""

import os
import requests
from requests_ntlm import HttpNtlmAuth
import csv
import time
import io
from pathlib import Path
from datetime import datetime

# ─── 配置区（优先读环境变量，回退到硬编码值）────────────────────────────────
CONFIG = {
    "report_server": "http://10.70.35.26/ReportServer",
    "report_path": "/imesreport/线边仓库存报表",  # SSRS 报表路径
    "username": os.environ.get("SSRS_USERNAME", "chenweijie"),
    "password": os.environ.get("SSRS_PASSWORD", "abcd,1234"),
    "timeout": 120,    # 报表导出可能较慢，给足时间
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

# ─── SSRS 直接导出 URL ────────────────────────────────────────────────────────
# 格式：/ReportServer?/报表路径&rs:Format=CSV&rs:ClearSession=true
# rs:ClearSession=true 避免使用缓存的旧会话参数
def build_export_url() -> str:
    from urllib.parse import quote
    encoded_path = quote(CONFIG["report_path"])
    return (
        f"{CONFIG['report_server']}?{encoded_path}"
        f"&rs:Format=CSV"
        f"&rs:ClearSession=true"
    )


def fetch_inventory_csv() -> str:
    """通过 NTLM 认证下载线边仓库存报表 CSV"""
    if not CONFIG["username"] or not CONFIG["password"]:
        raise ValueError(
            "请在 CONFIG 中填入 Windows 域账号和密码！\n"
            "格式示例：username='DOMAIN\\\\yourname' 或 username='yourname'"
        )

    url = build_export_url()
    auth = HttpNtlmAuth(CONFIG["username"], CONFIG["password"])

    print(f"[INFO] 正在请求 SSRS 报表导出...")
    print(f"[INFO] URL: {url}")

    resp = requests.get(
        url,
        auth=auth,
        timeout=CONFIG["timeout"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,text/plain,*/*",
        },
    )

    if resp.status_code == 401:
        raise PermissionError("认证失败（401）：请检查用户名和密码是否正确")
    if resp.status_code == 404:
        raise FileNotFoundError(f"报表路径不存在（404）：{CONFIG['report_path']}")
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    print(f"[INFO] 响应状态: {resp.status_code}  Content-Type: {content_type}  大小: {len(resp.content)} bytes")

    return resp.text


def parse_and_save(csv_text: str, output_filename: str = None) -> Path:
    """解析 CSV 内容并保存到文件"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = output_filename or f"线边仓库存报表_{ts}.csv"
    out_path = OUTPUT_DIR / filename

    # SSRS 导出的 CSV 可能有 BOM 头，统一用 utf-8-sig 处理
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_text)

    # 统计行数做健康检查
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    print(f"[INFO] 解析完成：{len(rows)} 条记录，字段：{list(reader.fieldnames or [])[:5]}...")
    print(f"[SAVE] CSV → {out_path}")

    # 同时保存固定文件名供后续脚本引用
    latest_path = OUTPUT_DIR / "inventory_latest.csv"
    with open(latest_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_text)
    print(f"[SAVE] CSV → {latest_path}")

    return out_path


def run():
    try:
        csv_text = fetch_inventory_csv()
        parse_and_save(csv_text)
        print("[OK] 线边仓库存报表更新完成")
    except ValueError as e:
        print(f"[CONFIG ERROR] {e}")
    except PermissionError as e:
        print(f"[AUTH ERROR] {e}")
    except requests.RequestException as e:
        print(f"[NETWORK ERROR] {e}")


if __name__ == "__main__":
    run()
