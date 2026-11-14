# -*- coding: utf-8 -*-
"""配置读取：config.json（公开、入库） + config.local.json（本机密钥，不入库） + 环境变量。"""
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
LOCAL_FILE = ROOT / "config.local.json"
DATA_DIR = ROOT / "data"

# 只存在 config.local.json 里的敏感项
SECRET_KEYS = ("claude_api_key", "ieee_api_key", "serpapi_key", "s2_api_key", "openalex_api_key",
               "owner_password_hash")
# 网页“设置”里允许修改的项
EDITABLE_KEYS = SECRET_KEYS + (
    "ai_backend", "claude_base_url", "claude_model", "ai_model", "ai_effort", "ai_context_chars",
    "openalex_mailto", "default_sources",
)
ENV_OVERRIDES = {
    "claude_base_url": "CLAUDE_PROXY_URL",
    "claude_api_key": "CLAUDE_PROXY_KEY",
    "ieee_api_key": "IEEE_API_KEY",
    "serpapi_key": "SERPAPI_KEY",
    "s2_api_key": "S2_API_KEY",
    "openalex_api_key": "OPENALEX_API_KEY",
    "ai_backend": "AI_BACKEND",
    "ai_model": "AI_MODEL",
}
DEFAULTS = {
    "ai_backend": "auto",  # auto：本机装了并登录了 Claude Code 就走订阅（claude -p），否则走 claude_base_url
    "claude_base_url": "http://localhost:8787",
    "claude_api_key": "unused",
    "claude_model": "haiku",  # 订阅论文的批量总结
    "ai_model": "claude-opus-5-5",  # AI 解读与伴读对话
    "ai_effort": "medium",
    "ai_context_chars": 100000,
    "default_sources": ["arxiv", "s2", "openalex", "ieee", "scholar"],
    "openalex_mailto": "",
}

_lock = threading.Lock()


def _read(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def load():
    cfg = dict(DEFAULTS)
    cfg.update(_read(CONFIG_FILE))
    cfg.update(_read(LOCAL_FILE))
    for key, env in ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


def get(key, default=None):
    return load().get(key, default)


def save_local(updates):
    """把网页设置写入 config.local.json；空字符串表示清除该项。"""
    with _lock:
        local = _read(LOCAL_FILE)
        for key, value in updates.items():
            if key not in EDITABLE_KEYS:
                continue
            if value in ("", None):
                local.pop(key, None)
            else:
                local[key] = value
        LOCAL_FILE.write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")


def public_settings():
    """给前端看的设置：密钥只返回是否已配置。"""
    cfg = load()
    out = {k: cfg.get(k) for k in EDITABLE_KEYS if k not in SECRET_KEYS}
    for k in SECRET_KEYS:
        val = cfg.get(k) or ""
        out[k] = bool(val) and val != "unused"
    return out
