# -*- coding: utf-8 -*-
"""一键更新: 抓取新论文 + 用 claude -p 生成中文总结。"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

for script in ("fetch_papers.py", "summarize.py"):
    print(f"\n===== 运行 {script} =====")
    ret = subprocess.run([sys.executable, str(HERE / script)]).returncode
    if ret != 0:
        sys.exit(f"{script} 失败 (exit {ret})")

print("\n更新完成。运行 `python -m http.server 8303` 后打开 http://localhost:8303 查看网站。")
