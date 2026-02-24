"""
HZERO 平台 Token 自动刷新
支持 IMES（client: IMES-MXC）和 NWMS（client: hzero-nwms-prd）
检测到 401 时自动登录获取新 Token 并更新 .env
"""

import os
import re
import base64
import logging
from pathlib import Path
from urllib.parse import quote

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
OAUTH_BASE      = "http://10.80.35.11:8080/oauth"
PUBLIC_KEY_B64  = (
    "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAJL0JkqsUoK6kt3JyogsgqNp9VDGDp+t3ZAGMbVo"
    "MPdHNT2nfiIVh9ZMNHF7g2XiAa8O8AQWyh2PjMR0NiUSVQMCAwEAAQ=="
)

IMES_CLIENT     = "IMES-MXC"
IMES_REDIRECT   = "http://10.60.35.11:30088"

NWMS_CLIENT     = "hzero-nwms-prd"
NWMS_REDIRECT   = "http://10.80.35.11:91/"

ENV_FILE        = Path(__file__).parent.parent.parent / ".env"

# ── 核心函数 ──────────────────────────────────────────────────────────────────
def _encrypt_password(password: str) -> str:
    key_der = base64.b64decode(PUBLIC_KEY_B64)
    pub_key = serialization.load_der_public_key(key_der)
    encrypted = pub_key.encrypt(password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def _fetch_token(username: str, password: str, client_id: str, redirect_uri: str) -> str | None:
    """登录 HZERO 并通过 OAuth2 Implicit Flow 获取 access_token"""
    s = requests.Session()
    s.get(f"{OAUTH_BASE}/login", timeout=10)
    enc_pwd = _encrypt_password(password)
    s.post(f"{OAUTH_BASE}/login",
           data={"username": username, "password": enc_pwd},
           allow_redirects=True, timeout=10)

    uri_encoded = quote(redirect_uri, safe="")
    resp = s.get(
        f"{OAUTH_BASE}/oauth/authorize?response_type=token"
        f"&client_id={client_id}&redirect_uri={uri_encoded}",
        allow_redirects=False, timeout=10
    )
    location = resp.headers.get("Location", "")
    m = re.search(r"access_token=([^&#]+)", location)
    return m.group(1) if m else None


def _update_env(key: str, value: str) -> None:
    """原地更新 .env 文件中的指定 key，不影响其他内容"""
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"{key}={value}\n")
        return

    lines = ENV_FILE.read_text().splitlines(keepends=True)
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    ENV_FILE.write_text("".join(lines))


# ── 对外接口 ──────────────────────────────────────────────────────────────────
def refresh_imes_token() -> str:
    """重新登录获取 IMES Token 并写入 .env 与环境变量"""
    username = os.environ.get("HZERO_USERNAME", "20252471")
    password = os.environ.get("HZERO_PASSWORD", "asd123")

    logger.info("[TokenManager] 正在刷新 IMES Token...")
    token = _fetch_token(username, password, IMES_CLIENT, IMES_REDIRECT)
    if not token:
        raise RuntimeError("IMES Token 刷新失败，请检查账号密码或网络连接")

    _update_env("IMES_TOKEN", token)
    os.environ["IMES_TOKEN"] = token
    logger.info("[TokenManager] IMES Token 已更新")
    return token


def refresh_nwms_token() -> str:
    """重新登录获取 NWMS Token 并写入 .env 与环境变量"""
    username = os.environ.get("HZERO_USERNAME", "20252471")
    password = os.environ.get("HZERO_PASSWORD", "asd123")

    logger.info("[TokenManager] 正在刷新 NWMS Token...")
    token = _fetch_token(username, password, NWMS_CLIENT, NWMS_REDIRECT)
    if not token:
        raise RuntimeError("NWMS Token 刷新失败，请检查账号密码或网络连接")

    _update_env("NWMS_TOKEN", token)
    os.environ["NWMS_TOKEN"] = token
    logger.info("[TokenManager] NWMS Token 已更新")
    return token


def ensure_imes_token() -> str:
    """返回当前有效的 IMES Token，失效自动刷新"""
    token = os.environ.get("IMES_TOKEN", "")
    if not token:
        return refresh_imes_token()
    return token


def ensure_nwms_token() -> str:
    """返回当前有效的 NWMS Token，失效自动刷新"""
    token = os.environ.get("NWMS_TOKEN", "")
    if not token:
        return refresh_nwms_token()
    return token
