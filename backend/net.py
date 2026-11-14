# -*- coding: utf-8 -*-
"""HTTP 工具：带重试的 GET/POST。"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "PaperReader/2.0 (personal research reading site; python-urllib)"


class HTTPFail(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def build_url(url, params=None):
    if not params:
        return url
    params = {k: v for k, v in params.items() if v not in (None, "")}
    return f"{url}?{urllib.parse.urlencode(params)}"


def request(url, params=None, headers=None, data=None, method=None, timeout=30, retries=2, backoff=2.0):
    """返回 (bytes, content_type)。429/5xx/网络错误自动重试。"""
    full = build_url(url, params)
    hdrs = {"User-Agent": UA, **(headers or {})}
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(full, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", errors="replace")
            last = HTTPFail(f"HTTP {e.code}: {body}", e.code)
            if e.code not in (429, 500, 502, 503, 504):
                raise last from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = HTTPFail(f"网络错误: {getattr(e, 'reason', e)}")
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise last


def get_text(url, params=None, headers=None, timeout=30, retries=2):
    body, _ = request(url, params, headers, timeout=timeout, retries=retries)
    return body.decode("utf-8", errors="replace")


def get_json(url, params=None, headers=None, timeout=30, retries=2):
    return json.loads(get_text(url, params, headers, timeout, retries))


def post_json(url, payload, headers=None, timeout=30, retries=1):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body, _ = request(url, None, {"Content-Type": "application/json", **(headers or {})},
                      data=data, method="POST", timeout=timeout, retries=retries)
    return json.loads(body.decode("utf-8", errors="replace"))
