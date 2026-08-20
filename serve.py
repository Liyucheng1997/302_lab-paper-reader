# -*- coding: utf-8 -*-
"""论文阅读网站服务器: 静态页面 + 更新 API。

用法: python serve.py [端口]   (默认 8303)
API:
  POST /api/update  body: {"action": "all" | "fetch" | "summarize"}  启动后台更新任务
  GET  /api/status  返回 {"running", "action", "log", "exit_code"}
"""
import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                env=env,
            )
            for line in proc.stdout:
                append_log(line.rstrip())
            exit_code = proc.wait()
            if exit_code != 0:
                append_log(f"{script} 失败 (exit {exit_code})")
                break
        if exit_code == 0:
            append_log("✅ 更新完成")
    except Exception as e:  # noqa: BLE001
        append_log(f"❌ 出错: {e}")
        exit_code = -1
    finally:
        with job_lock:
            job["running"] = False
            job["exit_code"] = exit_code


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):  # 静音访问日志
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            with job_lock:
                self._send_json(dict(job))
            return
        super().do_GET()

    def end_headers(self):
        # 数据文件禁止缓存，保证更新后前端拿到最新内容
        if self.path.startswith("/data/") or self.path.endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/update":
            self._send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        action = payload.get("action", "all")
        if action not in SCRIPTS:
            self._send_json({"error": f"未知 action: {action}"}, 400)
            return
        with job_lock:
            if job["running"]:
                self._send_json({"error": "已有更新任务在运行中"}, 409)
                return
            job.update(running=True, action=action, log=[], exit_code=None)
        threading.Thread(target=run_job, args=(action,), daemon=True).start()
        self._send_json({"ok": True, "action": action})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8303
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"论文阅读网站: http://localhost:{port}  (Ctrl+C 停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
