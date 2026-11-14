# -*- coding: utf-8 -*-
"""访问身份：访客匿名 id（签名 Cookie） + 站长密码解锁（签名 Cookie） + 简单限流。"""
import hashlib
import hmac
import os
import secrets
import threading
import time

from . import config

OWNER_COOKIE = "pr_owner"
UID_COOKIE = "pr_uid"
OWNER_DAYS = 90
SECRET_FILE = config.DATA_DIR / "secret.key"

_lock = threading.Lock()
_secret = None


def secret():
    global _secret
    if _secret is None:
        env = os.environ.get("SESSION_SECRET")
        if env:
            _secret = env.encode()
        else:
            config.DATA_DIR.mkdir(exist_ok=True)
            if not SECRET_FILE.exists():
                SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
            _secret = SECRET_FILE.read_text(encoding="utf-8").strip().encode()
    return _secret


def _sig(payload):
    return hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def sign(payload):
    return f"{payload}.{_sig(payload)}"


def unsign(token):
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    return payload if hmac.compare_digest(sig, _sig(payload)) else None


# ---------------- 密码 ----------------

def hash_password(pw, iterations=240000):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2${iterations}${salt}${h}"


def password_hash():
    return os.environ.get("OWNER_PASSWORD_HASH") or config.load().get("owner_password_hash") or ""


def verify_password(pw):
    stored = password_hash()
    try:
        _, it, salt, h = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), salt.encode(), int(it)).hex()
    return hmac.compare_digest(calc, h)


def set_password(pw):
    if len(pw or "") < 4:
        raise ValueError("密码至少 4 位")
    config.save_local({"owner_password_hash": hash_password(pw)})


# ---------------- Cookie 身份 ----------------

def owner_token():
    return sign(f"owner:{int(time.time()) + OWNER_DAYS * 86400}")


def is_owner_token(token):
    payload = unsign(token)
    if not payload or not payload.startswith("owner:"):
        return False
    try:
        return int(payload.split(":", 1)[1]) > time.time()
    except ValueError:
        return False


def new_uid():
    return "u_" + secrets.token_hex(10)


def uid_from_token(token):
    payload = unsign(token)
    return payload if payload and payload.startswith("u_") else None


# ---------------- 限流 ----------------

_hits = {}


def allow(key, limit, window):
    """window 秒内最多 limit 次。"""
    now = time.time()
    with _lock:
        arr = [t for t in _hits.get(key, []) if now - t < window]
        if len(arr) >= limit:
            _hits[key] = arr
            return False
        arr.append(now)
        _hits[key] = arr
        if len(_hits) > 20000:  # 防止内存无限增长
            for k in list(_hits)[:10000]:
                _hits.pop(k, None)
        return True


_fails = {}


def login_blocked(ip):
    """密码错误限流：同一 IP 15 分钟内最多错 5 次；全站 1 小时内最多错 30 次。返回需等待秒数（0 表示可以尝试）。"""
    now = time.time()
    with _lock:
        mine = [t for t in _fails.get(ip, []) if now - t < 900]
        everyone = [t for t in _fails.get("*", []) if now - t < 3600]
        _fails[ip], _fails["*"] = mine, everyone
        if len(mine) >= 5:
            return int(900 - (now - mine[0])) + 1
        if len(everyone) >= 30:
            return int(3600 - (now - everyone[0])) + 1
        return 0


def login_failed(ip):
    with _lock:
        _fails.setdefault(ip, []).append(time.time())
        _fails.setdefault("*", []).append(time.time())
