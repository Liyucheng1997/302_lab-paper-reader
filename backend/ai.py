# -*- coding: utf-8 -*-
"""AI 解读与伴读对话。

两类 AI：
1. 站长的 AI（输入密码解锁）：默认走本机 Claude Code 订阅（`claude -p`，算订阅额度，不花 API 的钱）；
   本机没装 / 没登录时走 Anthropic 兼容接口（本机反代或 api.anthropic.com，配置 claude_base_url）。
   默认模型 Claude Opus 5.5，effort = medium。
2. 访客自己的 API：浏览器每次请求带上（Anthropic 或 OpenAI 兼容格式），服务器只转发、不保存。
"""
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config, fulltext

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


class AIError(Exception):
    def __init__(self, message, code="failed"):
        super().__init__(message)
        self.code = code


DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"


# ================= 提供方 =================

def owner_provider():
    cfg = config.load()
    backend = (cfg.get("ai_backend") or "auto").lower()
    if backend == "auto":
        backend = "cli" if probe()["ok"] else "proxy"
    return {
        "kind": backend,  # cli / proxy
        "format": "anthropic",
        "base": cfg.get("claude_base_url") or "http://localhost:8787",
        "key": cfg.get("claude_api_key") or "unused",
        "model": cfg.get("ai_model") or DEFAULT_MODEL,
        "effort": cfg.get("ai_effort") or DEFAULT_EFFORT,
        "owner": True,
    }


def custom_provider(fmt, base, key, model):
    """访客自己的 API。base 必须是公网 https 地址（防止借服务器访问内网）。"""
    fmt = (fmt or "anthropic").lower()
    if fmt not in ("anthropic", "openai"):
        raise AIError("API 格式只能是 anthropic 或 openai")
    base = (base or "").strip().rstrip("/")
    if not base:
        base = "https://api.anthropic.com" if fmt == "anthropic" else ""
    if not base:
        raise AIError("请填写 API 地址")
    if not key:
        raise AIError("请填写 API Key")
    if not model:
        raise AIError("请填写模型名称")
    check_public_url(base)
    return {"kind": "custom", "format": fmt, "base": base, "key": key.strip(), "model": model.strip(),
            "effort": None, "owner": False}


def check_public_url(url):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not u.hostname:
        raise AIError("API 地址必须以 https:// 开头")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise AIError(f"解析不了域名 {u.hostname}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise AIError("API 地址不能指向内网")


def provider_label(p):
    if p["kind"] == "cli":
        return f"{p['model']} · Claude 订阅"
    if p["kind"] == "proxy":
        return f"{p['model']} · 站长 API"
    return f"{p['model']} · 自定义 API"


# ================= 本机 Claude Code（订阅） =================

_probe = {"at": 0, "data": None}
_probe_lock = threading.Lock()
_cool = {"until": 0, "reason": ""}
_sem = threading.BoundedSemaphore(max(1, int(os.environ.get("AI_SUB_CONCURRENCY") or 2)))
LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|too many requests|overloaded|529|429", re.I)


def find_bin():
    exe = "claude.exe" if os.name == "nt" else "claude"
    home = Path.home()
    cands = [os.environ.get("CLAUDE_BIN", "").strip(), str(home / ".local" / "bin" / exe),
             str(home / ".claude" / "local" / exe), shutil.which("claude") or "",
             "/usr/local/bin/claude", "/usr/bin/claude"]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def _cli_env():
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        env.pop(k, None)  # 否则 claude 会用 key 计费，而不是订阅
    env["DISABLE_AUTOUPDATER"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def _cli_dir():
    # 空目录里跑：不读到项目的 CLAUDE.md
    d = Path(tempfile.gettempdir()) / "paper-reader-claude"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _do_probe():
    b = find_bin()
    if not b:
        return {"ok": False, "bin": None, "plan": None, "reason": "本机没装 Claude Code"}
    try:
        r = subprocess.run([b, "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=25, env=_cli_env(), cwd=str(_cli_dir()))
        s = json.loads(r.stdout[r.stdout.index("{"):])
    except Exception:  # noqa: BLE001
        return {"ok": False, "bin": b, "plan": None, "reason": "Claude Code 打不开（检查不了登录状态）"}
    if not s.get("loggedIn"):
        return {"ok": False, "bin": b, "plan": None, "reason": "本机 Claude Code 还没登录（在 .env 配置 CLAUDE_CODE_OAUTH_TOKEN，或运行 claude 后 /login）"}
    if "api" in (s.get("authMethod") or "").lower() or s.get("apiKeySource"):
        return {"ok": False, "bin": b, "plan": None, "reason": "本机 Claude Code 登录的是 API key，不是订阅"}
    return {"ok": True, "bin": b, "plan": s.get("subscriptionType"), "reason": ""}


def probe(force=False):
    with _probe_lock:
        d = _probe["data"]
        ttl = 600 if d and d["ok"] else 120
        if force or not d or time.time() - _probe["at"] > ttl:
            _probe["data"] = _do_probe()
            _probe["at"] = time.time()
        return _probe["data"]


def owner_status():
    cfg = config.load()
    backend = (cfg.get("ai_backend") or "auto").lower()
    model = cfg.get("ai_model") or DEFAULT_MODEL
    effort = cfg.get("ai_effort") or DEFAULT_EFFORT
    if backend in ("auto", "cli"):
        p = probe()
        if p["ok"]:
            if time.time() < _cool["until"]:
                return {"ok": False, "via": "cli", "text": f"Claude 订阅{_cool['reason']}用完了，{_hm(_cool['until'])} 左右恢复"}
            plan = {"max": "Max", "pro": "Pro"}.get(p["plan"] or "", p["plan"] or "")
            return {"ok": True, "via": "cli", "text": f"走本机 Claude 订阅{f'（{plan}）' if plan else ''} · {model} · {effort}"}
        if backend == "cli":
            return {"ok": False, "via": "cli", "text": p["reason"]}
    return {"ok": True, "via": "proxy", "text": f"走 Anthropic 兼容接口 {cfg.get('claude_base_url')} · {model}"}


def _hm(ts):
    return time.strftime("%H:%M", time.localtime(ts))


def run_cli(system, user_text, model, effort=None, on_text=None, timeout=900):
    """跑一次 claude -p（stream-json 进出），返回最终文本。on_text 收到流式片段。"""
    p = probe()
    if not p["ok"]:
        raise AIError(p["reason"] or "本机没有 Claude 订阅")
    if time.time() < _cool["until"]:
        raise AIError(f"Claude 订阅{_cool['reason']}用完了，{_hm(_cool['until'])} 左右恢复", "busy")
    d = _cli_dir()
    fd, sys_file = tempfile.mkstemp(prefix="sys-", suffix=".md", dir=str(d))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(system)
    args = [p["bin"], "-p", "--verbose", "--input-format", "stream-json", "--output-format", "stream-json",
            "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
            "--model", model, "--tools", "", "--no-session-persistence", "--system-prompt-file", sys_file]
    if effort:
        args += ["--effort", effort]
    if on_text:
        args.append("--include-partial-messages")
    acquired = _sem.acquire(timeout=120)
    if not acquired:
        os.unlink(sys_file)
        raise AIError("AI 正忙（同时在跑的任务太多），稍后再试", "busy")
    proc = None
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", env=_cli_env(), cwd=str(d))
        killer = threading.Timer(timeout, proc.kill)
        killer.start()
        err_buf = []
        threading.Thread(target=lambda: err_buf.append(proc.stderr.read()), daemon=True).start()
        proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": user_text}},
                                    ensure_ascii=False) + "\n")
        proc.stdin.close()
        result, rejected, streamed = None, None, []
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "stream_event" and on_text:
                e = ev.get("event") or {}
                delta = e.get("delta") or {}
                if e.get("type") == "content_block_delta" and delta.get("type") == "text_delta" and delta.get("text"):
                    streamed.append(delta["text"])
                    on_text(delta["text"])
            elif t == "rate_limit_event":
                info = ev.get("rate_limit_info") or {}
                if info.get("status") == "rejected":
                    rejected = info
            elif t == "result":
                result = ev
        proc.wait()
        killer.cancel()
        err = "".join(err_buf).strip()
        r = result or {}
        text = " ".join(str(x) for x in [r.get("result"), *(r.get("errors") or []), err] if x)[:300]
        if rejected or r.get("api_error_status") == 429 or (r.get("is_error") and LIMIT_RE.search(text)):
            until = (rejected or {}).get("resetsAt") or 0
            until = until if until > time.time() else time.time() + 900
            kind = (rejected or {}).get("rateLimitType") or ""
            _cool["until"] = until
            _cool["reason"] = "5 小时额度" if kind == "five_hour" else ("每周额度" if kind.startswith("seven_day") else "额度")
            raise AIError(f"Claude 订阅{_cool['reason']}用完了，{_hm(until)} 左右恢复", "busy")
        if not result:
            if re.search(r"not logged in|login|authenticat|401", err, re.I):
                _probe["data"] = None
            raise AIError(f"Claude Code 出错了：{err[:200] or '没有输出'}")
        if r.get("is_error") or r.get("subtype") != "success":
            if re.search(r"not logged in|login|authenticat|401|403", text, re.I):
                _probe["data"] = None
                raise AIError(f"Claude Code 登录失效了：{text}")
            raise AIError(f"Claude Code 出错了：{text or r.get('subtype')}")
        if r.get("stop_reason") == "refusal":
            raise AIError("AI 没有回答这个问题", "refusal")
        return r.get("result") or "".join(streamed)
    finally:
        _sem.release()
        if proc and proc.poll() is None:
            proc.kill()
        try:
            os.unlink(sys_file)
        except OSError:
            pass


# ================= Anthropic 兼容接口（SDK） =================

def _sdk_client(p):
    if anthropic is None:
        raise AIError("服务器未安装 anthropic SDK（pip install anthropic）")
    base = re.sub(r"/v1$", "", p["base"].rstrip("/"))
    return anthropic.Anthropic(base_url=base, api_key=p["key"], timeout=600.0, max_retries=1)


def _sdk_kwargs(p, system, messages, max_tokens):
    kw = {"model": p["model"], "max_tokens": max_tokens, "messages": messages}
    if system:
        kw["system"] = system
    if "api.anthropic.com" in p["base"]:
        extra = {}
        if p.get("effort"):
            extra["output_config"] = {"effort": p["effort"]}
        if p["model"] in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"):
            # 拒答时由服务端自动换模型重试
            extra["fallbacks"] = "default"
            kw["extra_headers"] = {"anthropic-beta": "server-side-fallback-2026-07-01"}
        if extra:
            kw["extra_body"] = extra
    return kw


def _sdk_error(e):
    if anthropic is not None:
        if isinstance(e, anthropic.APIConnectionError):
            return AIError("连接不上 AI 服务，请检查 API 地址")
        if isinstance(e, anthropic.AuthenticationError):
            return AIError("API Key 不对")
        if isinstance(e, anthropic.PermissionDeniedError):
            return AIError("这个 API Key 没有权限使用该模型")
        if isinstance(e, anthropic.NotFoundError):
            return AIError("模型名称或接口地址不对")
        if isinstance(e, anthropic.RateLimitError):
            return AIError("AI 服务限流，稍后再试", "busy")
        if isinstance(e, anthropic.APIStatusError):
            return AIError(f"AI 服务返回错误 {e.status_code}: {str(e.message)[:200]}")
    return AIError(f"AI 调用失败: {e}")


def _check_msg(msg):
    if msg.stop_reason == "refusal":
        raise AIError("AI 没有回答这个问题", "refusal")
    return "".join(b.text for b in msg.content if b.type == "text")


# ================= OpenAI 兼容接口 =================

def _openai_request(p, system, messages, max_tokens, stream):
    url = p["base"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    body = json.dumps({"model": p["model"], "messages": msgs, "max_tokens": max_tokens, "stream": stream},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {p['key']}"})
    try:
        return urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", errors="replace")
        msg = {401: "API Key 不对", 403: "没有权限使用该模型", 404: "模型名称或接口地址不对", 429: "AI 服务限流，稍后再试"}.get(e.code)
        raise AIError(msg or f"AI 服务返回错误 {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise AIError(f"连接不上 AI 服务：{getattr(e, 'reason', e)}") from None


# ================= 统一入口 =================

def complete(p, prompt, system=None, max_tokens=16000):
    messages = [{"role": "user", "content": prompt}]
    if p["kind"] == "cli":
        return run_cli(system or "", prompt, p["model"], p.get("effort"))
    if p["format"] == "openai":
        with _openai_request(p, system, messages, max_tokens, False) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise AIError("AI 返回的格式不对") from None
    try:
        return _check_msg(_sdk_client(p).messages.create(**_sdk_kwargs(p, system, messages, max_tokens)))
    except AIError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _sdk_error(e) from e


def stream(p, history, question, system, max_tokens=16000):
    """伴读对话流式输出。history 为此前对话 [{role, content}]，question 为本轮用户内容。"""
    if p["kind"] == "cli":
        # claude -p 不保留会话：把之前的对话整理成一段文字一起发
        text = question
        if history:
            lines = [f"{'我' if h['role'] == 'user' else 'AI'}：{h['content']}" for h in history[-16:]]
            text = "（以下是我们之前关于这篇论文的对话）\n\n" + "\n\n".join(lines) + f"\n\n（现在的问题）\n{question}"
        q_ = []
        done = threading.Event()
        box = {}

        def worker():
            try:
                box["text"] = run_cli(system, text, p["model"], p.get("effort"), on_text=q_.append)
            except Exception as e:  # noqa: BLE001
                box["err"] = e
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()
        sent = 0
        while not done.is_set() or sent < len(q_):
            if sent < len(q_):
                yield q_[sent]
                sent += 1
            else:
                done.wait(0.05)
        if "err" in box:
            raise box["err"] if isinstance(box["err"], AIError) else AIError(str(box["err"]))
        if sent == 0 and box.get("text"):
            yield box["text"]
        return

    messages = _alternate(history + [{"role": "user", "content": question}])
    if p["format"] == "openai":
        with _openai_request(p, system, messages, max_tokens, True) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta") or {}
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta.get("content"):
                    yield delta["content"]
        return
    client = _sdk_client(p)
    kw = _sdk_kwargs(p, system, messages, max_tokens)
    produced = False
    try:
        with client.messages.stream(**kw) as s:
            for t in s.text_stream:
                produced = True
                yield t
        return
    except Exception as e:  # noqa: BLE001
        if produced:
            raise _sdk_error(e) from e
        first = e
    try:  # 有的反代不支持流式：退回一次性返回
        yield _check_msg(client.messages.create(**kw))
    except AIError:
        raise
    except Exception:  # noqa: BLE001
        raise _sdk_error(first) from first


def _alternate(msgs):
    out = []
    for m in msgs[-21:]:
        if m["role"] not in ("user", "assistant") or not m["content"].strip():
            continue
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n\n" + m["content"]}
        else:
            out.append({"role": m["role"], "content": m["content"]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


# ================= 论文上下文 =================

def paper_header(p):
    lines = [f"标题: {p.get('title')}"]
    if p.get("authors"):
        lines.append("作者: " + ", ".join(p["authors"][:12]))
    if p.get("venue"):
        lines.append(f"发表: {p['venue']} {p.get('published') or ''}")
    elif p.get("published"):
        lines.append(f"日期: {p['published']}")
    if p.get("doi"):
        lines.append(f"DOI: {p['doi']}")
    return "\n".join(lines)


def paper_context(p, ft):
    limit = int(config.load().get("ai_context_chars") or 100000)
    body = fulltext.as_text(ft, limit) if ft.get("source") != "abstract" else f"## Abstract\n{p.get('abstract') or '（无摘要）'}"
    kind = {"arxiv-html": "全文（arXiv HTML 版）", "pdf": "全文（PDF 提取）"}.get(ft.get("source"), "仅摘要（未能获取全文）")
    return f"{paper_header(p)}\n内容来源: {kind}\n\n<paper>\n{body}\n</paper>"


# ================= 结构化解读 =================

ANALYZE_SYSTEM = """你是一位资深科研导师，擅长带研究生精读论文，覆盖控制、自动驾驶、车辆动力学、机器人、无人机、人工智能等领域。
你的任务是帮读者梳理论文的架构脉络、指出需要重点关注的地方。解读必须忠于原文，不编造实验数字；原文没有的信息写"原文未提及"。
全部用简体中文书写，专业术语首次出现时附英文原词。"""

ANALYZE_PROMPT = """请精读下面这篇论文，输出一个 JSON 对象（只输出 JSON，不要 markdown 代码块或其他文字），结构如下：

{{
  "one_line": "一句话说清论文做了什么、核心贡献是什么（50 字以内）",
  "background": "研究背景与动机（2-4 句）",
  "problem": "要解决的具体问题，以及现有方法的不足",
  "contributions": ["贡献 1", "贡献 2", "..."],
  "structure": [
    {{"section": "章节名（与原文对应，如 1 Introduction）", "role": "这一节在全文论证中的作用", "summary": "这一节讲了什么（1-3 句）", "children": [{{"section": "子节", "summary": "..."}}]}}
  ],
  "logic_chain": ["问题", "关键洞察", "方法设计", "实验验证", "结论"],
  "method": {{
    "overview": "方法整体思路（3-5 句，通俗）",
    "modules": [{{"name": "模块/步骤名", "desc": "做什么、为什么这么设计", "key_formula": "核心公式的含义（可选，可用 LaTeX，用 $...$ 包裹）"}}]
  }},
  "experiments": {{
    "setup": "数据集/仿真平台/实验对象/对比基线",
    "findings": ["主要结论 1（尽量带原文数字）", "..."]
  }},
  "focus": [
    {{"point": "需要重点关注的内容", "why": "为什么重要（创新点 / 难点 / 容易误解 / 可复用）", "where": "在原文哪一节或哪个公式/图"}}
  ],
  "limitations": ["局限或可质疑之处", "..."],
  "future": ["可延伸的研究方向或改进思路", "..."],
  "terms": [{{"term": "关键术语（英文）", "explain": "中文解释"}}],
  "prerequisites": ["读懂本文需要的前置知识"],
  "reading_guide": "建议的阅读顺序与时间分配（如：先看图 1 和第 3 节……）",
  "tags": ["中文技术标签", "..."],
  "difficulty": "入门 / 中等 / 较难 / 很难 之一"
}}

要求：structure 要覆盖论文的主要章节（只有摘要时按摘要的逻辑层次拆分），logic_chain 每一步写成一句具体的话，focus 给 3-6 条，terms 给 4-10 个。

{context}"""


def parse_json_obj(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise AIError("AI 输出中未找到 JSON")
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 常见问题：LaTeX 反斜杠未转义
        return json.loads(re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r"\\\\", raw))


def analyze(p, paper, ft):
    text = complete(p, ANALYZE_PROMPT.format(context=paper_context(paper, ft)), system=ANALYZE_SYSTEM)
    try:
        return parse_json_obj(text)
    except (json.JSONDecodeError, AIError) as e:
        raise AIError(f"AI 返回的解读格式有误，请重试（{e}）") from e


# ================= 伴读对话 =================

CHAT_SYSTEM = """你是读者的论文伴读助手。读者正在阅读下面这篇论文，会边读边向你提问。

回答原则：
- 以论文原文为依据，引用时注明出处章节（如"见 3.2 节"、"公式 (5)"）；原文没有的内容要明确说明是你的补充或推测。
- 解释要有层次：先给直观理解，再讲技术细节；必要时举例或类比。数学公式用 LaTeX，行内 $...$，独立公式 $$...$$。
- 读者选中原文片段提问时，先解释该片段本身，再联系上下文。
- 默认简体中文，使用 Markdown（小标题、列表、加粗），篇幅与问题相称，不说空话。

{analysis}

{context}"""


def chat_system(paper, ft, analysis):
    a = ""
    if analysis:
        a = "此前已为这篇论文做过结构化解读（供参考）：\n" + json.dumps(
            {k: analysis.get(k) for k in ("one_line", "contributions", "logic_chain", "focus") if analysis.get(k)},
            ensure_ascii=False)
    return CHAT_SYSTEM.format(analysis=a, context=paper_context(paper, ft))


def user_content(question, selection=None):
    if selection:
        return f"我选中了原文中的这段内容：\n> {selection.strip()[:3000]}\n\n{question}"
    return question
