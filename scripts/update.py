# -*- coding: utf-8 -*-
"""一键更新: 抓取新论文 → 批量生成中文总结 → 提前算好站长的推荐（打开首页就是新的）。"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

for script in ("fetch_papers.py", "summarize.py"):
    print(f"\n===== 运行 {script} =====", flush=True)
    ret = subprocess.run([sys.executable, str(HERE / script)]).returncode
    if ret != 0:
        sys.exit(f"{script} 失败 (exit {ret})")

print("\n===== 刷新站长的推荐 =====", flush=True)
try:
    from backend import recommend, store  # noqa: E402
    data = recommend.recommend(store.OWNER, refresh=True)
    print(f"推荐 {len(data['items'])} 篇，候选 {data.get('candidates', 0)} 篇，来源 {data.get('sources')}")
except Exception as e:  # noqa: BLE001  推荐失败不影响论文库更新
    print(f"推荐刷新失败: {e}")

print("\n更新完成。")
