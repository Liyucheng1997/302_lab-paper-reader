# -*- coding: utf-8 -*-
"""备份个人数据库 data/user.db（在线备份，不用停服务，gzip 压缩），并清理过期缓存。

用法: python scripts/backup.py [标签]      备份到 BACKUP_DIR（默认 ./backups）

保留策略：每日备份留最近 14 份 + 最近 8 周每周日一份；部署前备份留最近 5 份；手动备份留最近 5 份。
标签为 daily 时顺便清理缓存（检索结果、全文缓存、过期推荐、半年没来过的访客数据）。
"""
import gzip
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import store  # noqa: E402

KEEP = {"daily": 14, "pre-deploy": 5}
KEEP_OTHER = 5
WEEKS = 8


def retain(out_dir):
    files = sorted(out_dir.glob("user-*.db.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    groups = {}
    for f in files:
        tag = f.name.split("-", 3)[-1].removesuffix(".db.gz")
        groups.setdefault(tag, []).append(f)
    keep = set()
    for tag, fs in groups.items():
        keep.update(fs[:KEEP.get(tag, KEEP_OTHER)])
    # 每日备份额外保留最近 8 周里每周日的那份
    weekly = {}
    for f in groups.get("daily", []):
        t = time.localtime(f.stat().st_mtime)
        if t.tm_wday == 6:
            weekly.setdefault(time.strftime("%Y-%W", t), f)
    keep.update(list(weekly.values())[:WEEKS])
    for f in files:
        if f not in keep:
            f.unlink()
    for f in out_dir.glob("user-*.db"):  # 旧版未压缩的备份
        f.unlink()


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "manual"
    if not store.DB_FILE.exists():
        print("还没有数据库，跳过备份")
        return
    if tag == "daily":
        print("清理缓存:", store.prune(), f"数据库现在 {store.db_size_mb()} MB")
    out_dir = Path(os.environ.get("BACKUP_DIR") or ROOT / "backups")
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"user-{time.strftime('%Y%m%d-%H%M%S')}-{tag}.db.gz"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "user.db"
        store.backup_to(raw)
        with open(raw, "rb") as fi, gzip.open(dst, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)
    retain(out_dir)
    total = sum(f.stat().st_size for f in out_dir.glob("user-*.db.gz"))
    print(f"已备份到 {dst}（{dst.stat().st_size / 1e6:.2f} MB），备份目录共 {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
