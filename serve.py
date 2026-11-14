# -*- coding: utf-8 -*-
"""论文阅读网站服务器：静态页面（web/） + JSON API。

用法: python serve.py [端口]        （默认 127.0.0.1:8303；环境变量 HOST / PORT 可改）

访问身份：
- 访客：浏览器自动分配匿名 id，阅读记录 / 收藏 / 对话各自独立；可以用自己的 AI API。
- 站长：输入密码解锁，使用站长的 AI（本机 Claude 订阅），并可更新论文库、修改服务器设置。
"""
import json
import os
import re
import subprocess
import sys
import threading
import traceback
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from backend import ai, auth, config, engines, fulltext, recommend, store

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
MAX_BODY = 1024 * 1024

# ---------------- 后台更新任务（订阅抓取 + 批量总结） ----------------
SCRIPTS = {
    "fetch": ["fetch_papers.py"],
    "summarize": ["summarize.py"],
    "all": ["fetch_papers.py", "summarize.py"],
}
job = {"running": False, "action": None, "log": [], "exit_code": None}
job_lock = threading.Lock()


def append_log(line):
    with job_lock:
        job["log"].append(line)
        if len(job["log"]) > 500:
            del job["log"][:100]


def run_job(action):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    exit_code = 0
    try:
        for script in SCRIPTS[action]:
            append_log(f"===== 运行 {script} =====")
            proc = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "scripts" / script)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", cwd=str(ROOT), env=env,
            )
            for line in proc.stdout:
                append_log(line.rstrip())
            exit_code = proc.wait()
            if exit_code != 0:
                append_log(f"{script} 失败 (exit {exit_code})")
                break
        if exit_code == 0:
            append_log("✅ 更新完成")
            store.sync_feed(force=True)
    except Exception as e:  # noqa: BLE001
        append_log(f"❌ 出错: {e}")
        exit_code = -1
    finally:
        with job_lock:
            job["running"] = False
            job["exit_code"] = exit_code


# ---------------- 工具 ----------------

class ApiError(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class Ctx:
    """一次请求的身份。"""

    def __init__(self, ip, uid, owner, ai_headers):
        self.ip = ip
        self.uid = store.OWNER if owner else uid
        self.owner = owner
        self.ai_headers = ai_headers

    def need_owner(self):
        if not self.owner:
            raise ApiError("这个操作需要站长密码", 403, "need_owner")

    def limit(self, name, n, window=60):
        if not self.owner and not auth.allow(f"{name}:{self.ip}", n, window):
            raise ApiError("操作太频繁了，请稍后再试", 429)

    def provider(self):
        """本次请求用哪个 AI：访客自己的 API 优先，其次站长（需已解锁）。"""
        h = self.ai_headers
        if h.get("key"):
            try:
                return ai.custom_provider(h.get("format"), h.get("base"), h.get("key"), h.get("model"))
            except ai.AIError as e:
                raise ApiError(str(e), 400) from None
        if self.owner:
            return ai.owner_provider()
        raise ApiError("使用 AI 需要输入站长密码，或在「AI 设置」里填写你自己的 API", 403, "need_ai")


def need_paper(pid, save=False):
    """取论文；save=True 时把只在内存里的检索 / 推荐结果写进数据库（被打开、收藏、解读时）。"""
    if not pid:
        raise ApiError("缺少论文 id")
    p = store.save_paper(pid) if save else store.get_paper(pid)
    if not p:
        raise ApiError("找不到这篇论文（检索结果只临时保存，请重新检索）", 404)
    return p


def decorate(ctx, papers):
    """给论文列表附上当前用户的收藏/已读状态。"""
    favs = store.favorite_ids(ctx.uid)
    hist = store.history_map(ctx.uid)
    analyzed = store.analyzed_ids()
    out = []
    for p in papers:
        p = dict(p)
        p["_fav"] = p["id"] in favs
        p["_read"] = p["id"] in hist
        p["_analyzed"] = p["id"] in analyzed
        out.append(p)
    return out


def bibtex(p):
    authors = " and ".join(p.get("authors") or [])
    year = (p.get("published") or "")[:4]
    first = re.sub(r"[^A-Za-z]", "", ((p.get("authors") or ["anon"])[0].split() or ["anon"])[-1]) or "anon"
    word = re.sub(r"[^A-Za-z]", "", (p.get("title") or "paper").split()[0]) or "paper"
    key = f"{first.lower()}{year}{word.lower()}"
    kind = "article" if p.get("venue") and p.get("venue") != "arXiv" else "misc"
    fields = {"title": p.get("title"), "author": authors, "year": year}
    if kind == "article":
        fields["journal"] = p.get("venue")
    if p.get("doi"):
        fields["doi"] = p["doi"]
    if p.get("arxiv_id"):
        fields["eprint"] = p["arxiv_id"]
        fields["archivePrefix"] = "arXiv"
    fields["url"] = p.get("url")
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@{kind}{{{key},\n{body}\n}}"


def me(ctx):
    out = {"owner": ctx.owner, "has_password": bool(auth.password_hash())}
    if ctx.owner:
        out["ai"] = ai.owner_status()
    return out


# ---------------- API 处理 ----------------

def api_get(ctx, path, qs):
    g = lambda k, d=None: (qs.get(k) or [d])[0]  # noqa: E731

    if path == "/api/health":
        return {"ok": True}

    if path == "/api/status":
        with job_lock:
            return dict(job) if ctx.owner else {"running": job["running"], "action": job["action"], "log": [], "exit_code": None}

    if path == "/api/me":
        return me(ctx)

    if path == "/api/meta":
        cfg = config.load()
        feed = store.load_feed()
        counts = {}
        for p in feed.get("papers", []):
            counts[p.get("field")] = counts.get(p.get("field"), 0) + 1
        return {
            "fields": {k: {"name": v["name"], "count": counts.get(k, 0)} for k, v in cfg.get("fields", {}).items()},
            "feed_updated": feed.get("updated"),
            "feed_total": len(feed.get("papers", [])),
            "engines": engines.engine_info(),
            "default_sources": cfg.get("default_sources"),
            "me": me(ctx),
        }

    if path == "/api/feed":
        store.sync_feed()
        feed = store.load_feed()
        ids = [p["id"] for p in feed.get("papers", [])]
        papers = store.get_papers(ids)
        lst = [papers[i] for i in ids if i in papers]
        if g("field"):
            lst = [p for p in lst if p.get("field") == g("field")]
        return {"updated": feed.get("updated"), "papers": decorate(ctx, lst)}

    if path == "/api/search":
        q = (g("q") or "").strip()[:300]
        if not q:
            raise ApiError("请输入检索词")
        ctx.limit("search", 20)
        sources = [s for s in (g("sources") or "").split(",") if s] or None
        res = engines.search(q, sources=sources, limit=min(int(g("limit", 20)), 50), sort=g("sort", "relevance"),
                             year_from=g("year_from") or None)
        res["results"] = decorate(ctx, res["results"])
        return res

    if path == "/api/paper":
        p = need_paper(g("id"), save=True)
        pid = p["id"]
        return {
            "paper": decorate(ctx, [p])[0],
            "favorite": store.favorite_get(ctx.uid, pid),
            "history": store.history_map(ctx.uid).get(pid),
            "analysis": store.analysis_get(pid),
            "chat": store.chat_list(ctx.uid, pid),
            "has_fulltext": bool(store.fulltext_get(pid)),
            "pdf_url": fulltext.paper_pdf_url(p),
        }

    if path == "/api/fulltext":
        p = need_paper(g("id"))
        if not store.fulltext_get(p["id"]):
            ctx.limit("fulltext", 20)
        return fulltext.get(p, force=g("force") == "1" and ctx.owner)

    if path == "/api/similar":
        p = need_paper(g("id"))
        ctx.limit("similar", 20)
        res = recommend.similar(p)
        res["web"]["items"] = decorate(ctx, res["web"]["items"])
        res["keyword"] = [{"paper": decorate(ctx, [x["paper"]])[0], "score": x["score"]} for x in res["keyword"]]
        return res

    if path == "/api/recommend":
        refresh = g("refresh") == "1"
        if refresh:
            ctx.limit("rec", 6)
        res = dict(recommend.recommend(ctx.uid, refresh=refresh))
        res["items"] = [{**it, "paper": decorate(ctx, [it["paper"]])[0]} for it in res["items"]]
        return res

    if path == "/api/history":
        rows = store.history_list(ctx.uid)
        papers = store.get_papers([r["paper_id"] for r in rows])
        items = [{**r, "paper": decorate(ctx, [papers[r["paper_id"]]])[0]} for r in rows if r["paper_id"] in papers]
        return {"items": items}

    if path == "/api/folders":
        return {"folders": store.folders(ctx.uid)}

    if path == "/api/favorites":
        favs = store.favorites_all(ctx.uid)
        papers = store.get_papers(list(favs))
        items = [{"fav": f, "paper": decorate(ctx, [papers[pid]])[0]} for pid, f in favs.items() if pid in papers]
        all_tags = {}
        for it in items:
            for t in it["fav"]["tags"]:
                all_tags[t] = all_tags.get(t, 0) + 1
        return {"items": items, "folders": store.folders(ctx.uid), "tags": sorted(all_tags.items(), key=lambda kv: -kv[1])}

    if path == "/api/favorites/suggest":
        return {"suggestion": recommend.suggest_folder(ctx.uid, g("id"))}

    if path == "/api/settings":
        ctx.need_owner()
        return {"settings": config.public_settings(), "engines": engines.engine_info(), "ai": ai.owner_status()}

    raise ApiError("not found", 404)


def api_post(ctx, path, body):
    if path == "/api/unlock":
        if not auth.password_hash():
            raise ApiError("服务器还没有设置站长密码（运行 python scripts/set_password.py）", 400)
        wait = auth.login_blocked(ctx.ip)
        if wait:
            raise ApiError(f"密码错误次数太多，请 {max(1, wait // 60)} 分钟后再试", 429)
        if not auth.verify_password(str(body.get("password") or "")):
            auth.login_failed(ctx.ip)
            raise ApiError("密码不对", 403)
        return {"ok": True, "_set_owner": True}

    if path == "/api/lock":
        return {"ok": True, "_clear_owner": True}

    if path == "/api/update":
        ctx.need_owner()
        action = body.get("action", "all")
        if action not in SCRIPTS:
            raise ApiError(f"未知 action: {action}")
        with job_lock:
            if job["running"]:
                raise ApiError("已有更新任务在运行中", 409)
            job.update(running=True, action=action, log=[], exit_code=None)
        threading.Thread(target=run_job, args=(action,), daemon=True).start()
        return {"ok": True, "action": action}

    if path == "/api/history/open":
        need_paper(body.get("id"), save=True)
        store.history_open(ctx.uid, body["id"])
        return {"ok": True}

    if path == "/api/history/tick":
        store.history_tick(ctx.uid, body.get("id"), body.get("seconds"))
        return {"ok": True}

    if path == "/api/history/delete":
        store.history_delete(ctx.uid, body.get("id"))
        return {"ok": True}

    if path == "/api/folders/create":
        return {"id": store.folder_create(ctx.uid, body.get("name", "")), "folders": store.folders(ctx.uid)}

    if path == "/api/folders/rename":
        store.folder_rename(ctx.uid, int(body["id"]), body.get("name", ""))
        return {"folders": store.folders(ctx.uid)}

    if path == "/api/folders/delete":
        store.folder_delete(ctx.uid, int(body["id"]))
        return {"folders": store.folders(ctx.uid)}

    if path == "/api/favorites/set":
        need_paper(body.get("id"), save=True)
        fav = store.favorite_set(ctx.uid, body["id"], folder_ids=body.get("folder_ids"), note=body.get("note"),
                                 tags=body.get("tags"), status=body.get("status"))
        return {"favorite": fav, "folders": store.folders(ctx.uid)}

    if path == "/api/favorites/delete":
        store.favorite_delete(ctx.uid, body.get("id"))
        return {"ok": True, "folders": store.folders(ctx.uid)}

    if path == "/api/dismiss":
        need_paper(body.get("id"), save=True)
        store.dismiss(ctx.uid, body.get("id"))
        return {"ok": True}

    if path == "/api/analyze":
        p = need_paper(body.get("id"), save=True)
        cached = store.analysis_get(p["id"])
        if cached and not (body.get("force") and ctx.owner):
            return cached
        prov = ctx.provider()
        ctx.limit("ai", 20)
        ft = fulltext.get(p)
        try:
            data = ai.analyze(prov, p, ft)
        except ai.AIError as e:
            raise ApiError(str(e), 502, e.code) from None
        store.analysis_set(p["id"], data, ai.provider_label(prov), ft["source"])
        # 把 AI 标签回写到论文，供推荐算法使用
        if data.get("tags") and not (p.get("summary") or {}).get("tags"):
            s = p.get("summary") or {}
            store.upsert_paper({**p, "summary": {"tldr": s.get("tldr") or data.get("one_line", ""),
                                                 "points": s.get("points") or [], "tags": data["tags"][:4]}})
        return store.analysis_get(p["id"])

    if path == "/api/ai/test":
        prov = ctx.provider()
        ctx.limit("ai", 20)
        try:
            text = ai.complete(prov, "请只回复：OK", max_tokens=20)
        except ai.AIError as e:
            raise ApiError(str(e), 502) from None
        return {"ok": True, "reply": text.strip()[:100], "label": ai.provider_label(prov)}

    if path == "/api/chat/clear":
        store.chat_clear(ctx.uid, body.get("id"))
        return {"ok": True}

    if path == "/api/settings":
        ctx.need_owner()
        updates = dict(body)
        new_pw = updates.pop("owner_password", None)
        updates.pop("owner_password_hash", None)
        config.save_local(updates)
        if new_pw:
            auth.set_password(str(new_pw))
        ai.probe(force=True)
        return {"settings": config.public_settings(), "engines": engines.engine_info(), "ai": ai.owner_status()}

    raise ApiError("not found", 404)


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        pass

    # ---------- 身份 ----------
    def _ctx(self):
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1") and self.headers.get("X-Real-IP"):
            ip = self.headers["X-Real-IP"].strip()  # nginx 反代
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:  # noqa: BLE001
            pass
        val = lambda k: cookie[k].value if k in cookie else None  # noqa: E731
        owner = auth.is_owner_token(val(auth.OWNER_COOKIE))
        uid = auth.uid_from_token(val(auth.UID_COOKIE))
        self._set_cookies = []
        if not uid:
            uid = auth.new_uid()
            self._set_cookies.append(self._cookie(auth.UID_COOKIE, auth.sign(uid), 730 * 86400))
        h = {k: unquote(self.headers.get(f"X-AI-{k.capitalize()}") or "") for k in ("format", "base", "key", "model")}
        return Ctx(ip, uid, owner, h)

    def _cookie(self, name, value, max_age):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure}"

    def _send_cookies(self):
        for c in getattr(self, "_set_cookies", []):
            self.send_header("Set-Cookie", c)

    def end_headers(self):
        if self.path.endswith((".js", ".css", ".html")) or self.path == "/":
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, obj, status=200):
        if isinstance(obj, dict):
            if obj.pop("_set_owner", False):
                self._set_cookies.append(self._cookie(auth.OWNER_COOKIE, auth.owner_token(), auth.OWNER_DAYS * 86400))
            if obj.pop("_clear_owner", False):
                self._set_cookies.append(self._cookie(auth.OWNER_COOKIE, "", 0))
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cookies()
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError("请求太大", 413)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _guard(self, fn):
        try:
            self._json(fn())
        except (BrokenPipeError, ConnectionError):
            pass  # 浏览器已断开（换页、刷新），不用回应
        except ApiError as e:
            self._json({"error": str(e), "code": e.code}, e.status)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": f"服务器出错: {e}"}, 500)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            ctx = self._ctx()
            qs = parse_qs(url.query)
            if url.path == "/api/pdf":
                return self._pdf(ctx, qs)
            if url.path == "/api/export/bibtex":
                return self._bibtex(ctx, qs)
            return self._guard(lambda: api_get(ctx, url.path, qs))
        if url.path in ("/", "/index.html") or not (WEB / url.path.lstrip("/")).is_file():
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        ctx = self._ctx()
        if url.path == "/api/chat":
            return self._chat(ctx)
        self._guard(lambda: api_post(ctx, url.path, self._body()))

    # PDF 代理：同源后浏览器内置 PDF 阅读器可直接嵌入
    def _pdf(self, ctx, qs):
        try:
            p = need_paper((qs.get("id") or [None])[0])
            ctx.limit("pdf", 30)
            path = fulltext.pdf_path(p)
            if not path:
                raise ApiError("这篇论文没有可用的开放获取 PDF", 404)
            data = path.read_bytes()
        except ApiError as e:
            return self._json({"error": str(e)}, e.status)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"PDF 获取失败: {e}"}, 502)
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=86400")
        self._send_cookies()
        self.end_headers()
        self.wfile.write(data)

    def _bibtex(self, ctx, qs):
        folder = (qs.get("folder") or [""])[0]
        ids = (qs.get("ids") or [""])[0]
        favs = store.favorites_all(ctx.uid)
        if ids:
            pids = ids.split(",")[:500]
        elif folder:
            pids = [pid for pid, f in favs.items() if str(folder) in map(str, f["folder_ids"])]
        else:
            pids = list(favs)
        papers = store.get_papers(pids)
        data = ("\n\n".join(bibtex(papers[pid]) for pid in pids if pid in papers) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-bibtex; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="papers.bib"')
        self.send_header("Content-Length", str(len(data)))
        self._send_cookies()
        self.end_headers()
        self.wfile.write(data)

    # 伴读对话：SSE 流式输出
    def _chat(self, ctx):
        try:
            body = self._body()
            p = need_paper(body.get("id"), save=True)
            question = (body.get("message") or "").strip()[:8000]
            if not question:
                raise ApiError("消息不能为空")
            prov = ctx.provider()
            ctx.limit("ai", 20)
        except ApiError as e:
            return self._json({"error": str(e), "code": e.code}, e.status)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")  # nginx 不缓冲，逐字输出
        self.send_header("Connection", "close")
        self._send_cookies()
        self.end_headers()

        def send(obj):
            self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        pid = p["id"]
        try:
            send({"type": "status", "text": "正在读取论文全文…"})
            ft = fulltext.get(p)
            analysis = (store.analysis_get(pid) or {}).get("data")
            history = [{"role": h["role"], "content": h["content"]} for h in store.chat_list(ctx.uid, pid)]
            content = ai.user_content(question, body.get("selection"))
            system = ai.chat_system(p, ft, analysis)
            store.chat_add(ctx.uid, pid, "user", content)
            send({"type": "start", "source": ft["source"], "label": ai.provider_label(prov)})
            parts = []
            for chunk in ai.stream(prov, history, content, system):
                parts.append(chunk)
                send({"type": "delta", "text": chunk})
            answer = "".join(parts).strip()
            if answer:
                store.chat_add(ctx.uid, pid, "assistant", answer)
            send({"type": "done"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except ai.AIError as e:
            try:
                send({"type": "error", "text": str(e)})
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                send({"type": "error", "text": f"服务器出错: {e}"})
            except OSError:
                pass


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8303))
    store.conn()
    store.sync_feed()
    auth.secret()
    threading.Thread(target=lambda: print("启动清理:", store.prune(), flush=True), daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"论文阅读网站: http://{host}:{port}  (Ctrl+C 停止)", flush=True)
    if not auth.password_hash():
        print("提示：还没设置站长密码，运行 python scripts/set_password.py", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
