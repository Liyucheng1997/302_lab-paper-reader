# -*- coding: utf-8 -*-
"""SQLite 存储。

共享：论文缓存、全文缓存、AI 解读（同一篇论文只解析一次，所有人可看）。
按用户：阅读记录、收藏夹、对话、不感兴趣。用户 id：站长解锁后为 "owner"，访客为浏览器里的匿名 id。
"""
import json
import re
import sqlite3
import threading
import time
from collections import OrderedDict

from . import config

DB_FILE = config.DATA_DIR / "user.db"
FEED_FILE = config.DATA_DIR / "papers.json"
OWNER = "owner"
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers(
  id TEXT PRIMARY KEY, data TEXT NOT NULL, title_norm TEXT, doi TEXT, updated REAL);
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title_norm);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE TABLE IF NOT EXISTS analyses(
  paper_id TEXT PRIMARY KEY, data TEXT, model TEXT, source TEXT, created REAL);
CREATE TABLE IF NOT EXISTS fulltext(
  paper_id TEXT PRIMARY KEY, source TEXT, blocks TEXT, created REAL);
CREATE TABLE IF NOT EXISTS history(
  user_id TEXT NOT NULL, paper_id TEXT NOT NULL, first_read REAL, last_read REAL,
  read_count INTEGER DEFAULT 1, seconds INTEGER DEFAULT 0, PRIMARY KEY(user_id, paper_id));
CREATE TABLE IF NOT EXISTS folders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL, created REAL,
  sort INTEGER DEFAULT 0, UNIQUE(user_id, name));
CREATE TABLE IF NOT EXISTS favorites(
  user_id TEXT NOT NULL, paper_id TEXT NOT NULL, note TEXT DEFAULT '', tags TEXT DEFAULT '[]', added REAL,
  status TEXT DEFAULT 'todo', PRIMARY KEY(user_id, paper_id));
CREATE TABLE IF NOT EXISTS favorite_folders(
  user_id TEXT NOT NULL, paper_id TEXT NOT NULL, folder_id INTEGER NOT NULL,
  PRIMARY KEY(user_id, paper_id, folder_id));
CREATE TABLE IF NOT EXISTS chats(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, paper_id TEXT, role TEXT, content TEXT, created REAL);
CREATE INDEX IF NOT EXISTS idx_chats_user_paper ON chats(user_id, paper_id);
CREATE TABLE IF NOT EXISTS rec_cache(
  user_id TEXT PRIMARY KEY, data TEXT, created REAL);
CREATE TABLE IF NOT EXISTS dismissed(
  user_id TEXT NOT NULL, paper_id TEXT NOT NULL, created REAL, PRIMARY KEY(user_id, paper_id));
"""

# 第 1 版（单用户）的个人数据表：迁移时归到站长名下
_V1_TABLES = {
    "history": "paper_id, first_read, last_read, read_count, seconds",
    "folders": "id, name, created, sort",
    "favorites": "paper_id, note, tags, added, status",
    "favorite_folders": "paper_id, folder_id",
    "chats": "id, paper_id, role, content, created",
    "dismissed": "paper_id, created",
}

_lock = threading.RLock()
_conn = None
_feed_mtime = None

# 检索 / 推荐结果先放内存（不入库）；有人打开、收藏、解读时才写进数据库
_staged = OrderedDict()
STAGE_MAX = 5000


def norm_title(title):
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def norm_doi(doi):
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def _migrate(c):
    version = c.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    old = {}
    for table in _V1_TABLES:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
        if cols and "user_id" not in cols:
            c.execute(f"ALTER TABLE {table} RENAME TO _old_{table}")
            old[table] = True
    c.executescript(SCHEMA)
    for table in old:
        cols = _V1_TABLES[table]
        c.execute(f"INSERT INTO {table}(user_id, {cols}) SELECT '{OWNER}', {cols} FROM _old_{table}")
        c.execute(f"DROP TABLE _old_{table}")
    c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    c.commit()


def conn():
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(exist_ok=True)
        c = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        _migrate(c)
        c.executescript(SCHEMA)
        c.commit()
        _conn = c
    return _conn


def q(sql, args=(), one=False):
    with _lock:
        cur = conn().execute(sql, args)
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with _lock:
        cur = conn().execute(sql, args)
        conn().commit()
        return cur


def backup_to(path):
    """在线备份数据库（不用停服务）。"""
    with _lock:
        dst = sqlite3.connect(str(path))
        conn().backup(dst)
        dst.close()


# ---------------- 论文 ----------------

def _merge(old, new):
    """合并同一篇论文的两份记录：保留非空字段，摘要取较长者。"""
    out = dict(old)
    for k, v in new.items():
        if k in ("id",):
            continue
        if k == "abstract":
            if len(v or "") > len(out.get("abstract") or ""):
                out[k] = v
        elif k == "found_in":
            out[k] = sorted(set(out.get(k) or []) | set(v or []))
        elif k == "citations":
            if v is not None and (out.get(k) is None or v > out.get(k)):
                out[k] = v
        elif v not in (None, "", [], {}) and out.get(k) in (None, "", [], {}):
            out[k] = v
    return out


def _find_existing(p):
    row = q("SELECT data FROM papers WHERE id=?", (p["id"],), one=True)
    if row:
        return json.loads(row["data"])
    doi = norm_doi(p.get("doi"))
    if doi:
        row = q("SELECT data FROM papers WHERE doi=?", (doi,), one=True)
        if row:
            return json.loads(row["data"])
    tn = norm_title(p.get("title"))
    if len(tn) > 12:
        row = q("SELECT data FROM papers WHERE title_norm=?", (tn,), one=True)
        if row:
            return json.loads(row["data"])
    return None


def upsert_paper(p):
    """写入/合并论文，返回规范化后的记录（若与已有论文重复则沿用已有 id）。"""
    if not p.get("id") or not p.get("title"):
        return p
    with _lock:
        old = _find_existing(p)
        merged = _merge(old, p) if old else dict(p)
        if old:
            merged["id"] = old["id"]
        merged["doi"] = norm_doi(merged.get("doi"))
        x("INSERT OR REPLACE INTO papers(id,data,title_norm,doi,updated) VALUES(?,?,?,?,?)",
          (merged["id"], json.dumps(merged, ensure_ascii=False), norm_title(merged["title"]),
           merged["doi"] or None, time.time()))
        return merged


def upsert_many(papers):
    return [upsert_paper(p) for p in papers]


def get_paper(pid):
    sync_feed()
    row = q("SELECT data FROM papers WHERE id=?", (pid,), one=True)
    if row:
        return json.loads(row["data"])
    with _lock:
        p = _staged.get(pid)
    return dict(p) if p else None


def stage_paper(p):
    """检索 / 推荐得到的论文：库里已有就合并（沿用已有 id），没有就只放内存。"""
    if not p.get("id") or not p.get("title"):
        return p
    with _lock:
        if _find_existing(p):
            return upsert_paper(p)
        old = _staged.pop(p["id"], None)
        merged = _merge(old, p) if old else dict(p)
        merged["doi"] = norm_doi(merged.get("doi"))
        _staged[p["id"]] = merged
        while len(_staged) > STAGE_MAX:
            _staged.popitem(last=False)
        return dict(merged)


def stage_many(papers):
    return [stage_paper(p) for p in papers]


def save_paper(pid):
    """把内存里的论文写进数据库（被打开、收藏、解读、对话时调用）。返回论文。"""
    with _lock:
        p = _staged.pop(pid, None)
    if p:
        return upsert_paper(p)
    return get_paper(pid)


def get_papers(ids):
    sync_feed()
    if not ids:
        return {}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = q(f"SELECT id,data FROM papers WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        out.update({r["id"]: json.loads(r["data"]) for r in rows})
    return out


def all_papers():
    sync_feed()
    return [json.loads(r["data"]) for r in q("SELECT data FROM papers")]


def corpus_signature():
    row = q("SELECT COUNT(*) AS n, MAX(updated) AS m FROM papers", one=True)
    return (row["n"], row["m"])


def load_feed():
    if not FEED_FILE.exists():
        return {"updated": "", "papers": []}
    return json.loads(FEED_FILE.read_text(encoding="utf-8"))


def sync_feed(force=False):
    """把抓取脚本生成的 papers.json 导入数据库（文件变化时才重新导入）。"""
    global _feed_mtime
    if not FEED_FILE.exists():
        return
    mtime = FEED_FILE.stat().st_mtime
    if not force and mtime == _feed_mtime:
        return
    _feed_mtime = mtime
    feed = load_feed()
    with _lock:
        for p in feed.get("papers", []):
            p = dict(p)
            p.setdefault("found_in", ["feed"])
            if p["id"].startswith("arxiv:"):
                p.setdefault("arxiv_id", re.sub(r"v\d+$", "", p["id"][6:]))
            if "doi.org/" in (p.get("url") or ""):
                p.setdefault("doi", p["url"].split("doi.org/", 1)[1])
            upsert_paper(p)


# ---------------- 阅读记录（按用户） ----------------

def history_open(uid, pid):
    now = time.time()
    row = q("SELECT last_read FROM history WHERE user_id=? AND paper_id=?", (uid, pid), one=True)
    if row:
        # 30 分钟内重复打开不重复计次
        inc = 1 if now - (row["last_read"] or 0) > 1800 else 0
        x("UPDATE history SET last_read=?, read_count=read_count+? WHERE user_id=? AND paper_id=?", (now, inc, uid, pid))
    else:
        x("INSERT INTO history(user_id,paper_id,first_read,last_read,read_count,seconds) VALUES(?,?,?,?,1,0)",
          (uid, pid, now, now))


def history_tick(uid, pid, seconds):
    seconds = max(0, min(int(seconds or 0), 300))
    x("UPDATE history SET seconds=seconds+?, last_read=? WHERE user_id=? AND paper_id=?", (seconds, time.time(), uid, pid))


def history_list(uid, limit=500):
    rows = q("SELECT * FROM history WHERE user_id=? ORDER BY last_read DESC LIMIT ?", (uid, limit))
    return [dict(r) for r in rows]


def history_delete(uid, pid=None):
    if pid:
        x("DELETE FROM history WHERE user_id=? AND paper_id=?", (uid, pid))
    else:
        x("DELETE FROM history WHERE user_id=?", (uid,))


def history_map(uid):
    return {r["paper_id"]: dict(r) for r in q("SELECT * FROM history WHERE user_id=?", (uid,))}


# ---------------- 收藏夹（按用户） ----------------

def folders(uid):
    rows = q("""SELECT f.id, f.name, f.created, f.sort, COUNT(ff.paper_id) AS count
                FROM folders f LEFT JOIN favorite_folders ff ON ff.folder_id=f.id AND ff.user_id=f.user_id
                WHERE f.user_id=? GROUP BY f.id ORDER BY f.sort, f.created""", (uid,))
    return [dict(r) for r in rows]


def folder_create(uid, name):
    name = name.strip()[:60]
    if not name:
        raise ValueError("文件夹名不能为空")
    if len(folders(uid)) >= 200:
        raise ValueError("文件夹太多了")
    try:
        cur = x("INSERT INTO folders(user_id,name,created,sort) VALUES(?,?,?,?)", (uid, name, time.time(), int(time.time())))
    except sqlite3.IntegrityError:
        raise ValueError("已存在同名文件夹") from None
    return cur.lastrowid


def folder_rename(uid, fid, name):
    name = name.strip()[:60]
    if not name:
        raise ValueError("文件夹名不能为空")
    try:
        x("UPDATE folders SET name=? WHERE id=? AND user_id=?", (name, fid, uid))
    except sqlite3.IntegrityError:
        raise ValueError("已存在同名文件夹") from None


def folder_delete(uid, fid):
    x("DELETE FROM favorite_folders WHERE folder_id=? AND user_id=?", (fid, uid))
    x("DELETE FROM folders WHERE id=? AND user_id=?", (fid, uid))


def favorite_get(uid, pid):
    row = q("SELECT * FROM favorites WHERE user_id=? AND paper_id=?", (uid, pid), one=True)
    if not row:
        return None
    fav = dict(row)
    fav["tags"] = json.loads(fav["tags"] or "[]")
    fav["folder_ids"] = [r["folder_id"] for r in
                         q("SELECT folder_id FROM favorite_folders WHERE user_id=? AND paper_id=?", (uid, pid))]
    return fav


def favorite_set(uid, pid, folder_ids=None, note=None, tags=None, status=None):
    if not q("SELECT 1 FROM favorites WHERE user_id=? AND paper_id=?", (uid, pid), one=True):
        x("INSERT INTO favorites(user_id,paper_id,note,tags,added,status) VALUES(?,?,?,?,?,?)",
          (uid, pid, "", "[]", time.time(), "todo"))
    if note is not None:
        x("UPDATE favorites SET note=? WHERE user_id=? AND paper_id=?", (str(note)[:5000], uid, pid))
    if tags is not None:
        clean = [str(t).strip()[:30] for t in tags if str(t).strip()][:20]
        x("UPDATE favorites SET tags=? WHERE user_id=? AND paper_id=?", (json.dumps(clean, ensure_ascii=False), uid, pid))
    if status is not None and status in ("todo", "reading", "done"):
        x("UPDATE favorites SET status=? WHERE user_id=? AND paper_id=?", (status, uid, pid))
    if folder_ids is not None:
        x("DELETE FROM favorite_folders WHERE user_id=? AND paper_id=?", (uid, pid))
        valid = {f["id"] for f in folders(uid)}
        for fid in folder_ids:
            if int(fid) in valid:
                x("INSERT OR IGNORE INTO favorite_folders(user_id,paper_id,folder_id) VALUES(?,?,?)", (uid, pid, int(fid)))
    return favorite_get(uid, pid)


def favorite_delete(uid, pid):
    x("DELETE FROM favorite_folders WHERE user_id=? AND paper_id=?", (uid, pid))
    x("DELETE FROM favorites WHERE user_id=? AND paper_id=?", (uid, pid))


def favorites_all(uid):
    favs = {r["paper_id"]: dict(r) for r in q("SELECT * FROM favorites WHERE user_id=? ORDER BY added DESC", (uid,))}
    for f in favs.values():
        f["tags"] = json.loads(f["tags"] or "[]")
        f["folder_ids"] = []
    for r in q("SELECT paper_id, folder_id FROM favorite_folders WHERE user_id=?", (uid,)):
        if r["paper_id"] in favs:
            favs[r["paper_id"]]["folder_ids"].append(r["folder_id"])
    return favs


def favorite_ids(uid):
    return {r["paper_id"] for r in q("SELECT paper_id FROM favorites WHERE user_id=?", (uid,))}


# ---------------- AI 解读（共享） / 对话（按用户） / 全文（共享） ----------------

def analysis_get(pid):
    row = q("SELECT * FROM analyses WHERE paper_id=?", (pid,), one=True)
    if not row:
        return None
    return {"data": json.loads(row["data"]), "model": row["model"], "source": row["source"], "created": row["created"]}


def analysis_set(pid, data, model, source):
    x("INSERT OR REPLACE INTO analyses(paper_id,data,model,source,created) VALUES(?,?,?,?,?)",
      (pid, json.dumps(data, ensure_ascii=False), model, source, time.time()))


def analyzed_ids():
    return {r["paper_id"] for r in q("SELECT paper_id FROM analyses")}


def chat_list(uid, pid):
    return [dict(r) for r in q("SELECT id, role, content, created FROM chats WHERE user_id=? AND paper_id=? ORDER BY id",
                                (uid, pid))]


def chat_add(uid, pid, role, content):
    x("INSERT INTO chats(user_id,paper_id,role,content,created) VALUES(?,?,?,?,?)", (uid, pid, role, content, time.time()))


def chat_clear(uid, pid):
    x("DELETE FROM chats WHERE user_id=? AND paper_id=?", (uid, pid))


def chat_counts(uid):
    return {r["paper_id"]: r["n"] for r in
            q("SELECT paper_id, COUNT(*) AS n FROM chats WHERE user_id=? AND role='user' GROUP BY paper_id", (uid,))}


def fulltext_get(pid):
    row = q("SELECT * FROM fulltext WHERE paper_id=?", (pid,), one=True)
    if not row:
        return None
    if time.time() - (row["created"] or 0) > 86400:
        x("UPDATE fulltext SET created=? WHERE paper_id=?", (time.time(), pid))  # 记录最近使用，清理时保留常用的
    return {"source": row["source"], "blocks": json.loads(row["blocks"])}


def fulltext_set(pid, source, blocks):
    x("INSERT OR REPLACE INTO fulltext(paper_id,source,blocks,created) VALUES(?,?,?,?)",
      (pid, source, json.dumps(blocks, ensure_ascii=False), time.time()))


def dismiss(uid, pid):
    x("INSERT OR REPLACE INTO dismissed(user_id,paper_id,created) VALUES(?,?,?)", (uid, pid, time.time()))


def dismissed_ids(uid):
    return {r["paper_id"] for r in q("SELECT paper_id FROM dismissed WHERE user_id=?", (uid,))}


# ---------------- 推荐缓存 ----------------

def rec_cache_get(uid):
    row = q("SELECT data, created FROM rec_cache WHERE user_id=?", (uid,), one=True)
    if not row:
        return None
    return {"data": json.loads(row["data"]), "created": row["created"]}


def rec_cache_set(uid, data):
    x("INSERT OR REPLACE INTO rec_cache(user_id,data,created) VALUES(?,?,?)",
      (uid, json.dumps(data, ensure_ascii=False), time.time()))


# ---------------- 清理（每天由备份任务调用） ----------------

def prune(paper_days=60, fulltext_mb=500, rec_days=14, anon_days=180):
    """清理不再需要的缓存，返回各项删除数量。

    - 论文缓存：不在订阅论文库里、没有任何人读过 / 收藏 / 解读 / 对话过、超过 paper_days 天没更新的
    - 全文缓存：总量超过 fulltext_mb 时删最久没看的（被收藏的保留）
    - 推荐缓存：超过 rec_days 天的
    - 匿名访客：超过 anon_days 天没再来过的个人数据
    """
    out = {}
    now = time.time()
    feed_ids = [p["id"] for p in load_feed().get("papers", [])]
    with _lock:
        c = conn()
        c.execute("CREATE TEMP TABLE IF NOT EXISTS _keep(id TEXT PRIMARY KEY)")
        c.execute("DELETE FROM _keep")
        c.executemany("INSERT OR IGNORE INTO _keep(id) VALUES(?)", [(i,) for i in feed_ids])
        for t in ("history", "favorites", "chats", "dismissed", "analyses"):
            c.execute(f"INSERT OR IGNORE INTO _keep(id) SELECT paper_id FROM {t}")
        out["papers"] = c.execute("DELETE FROM papers WHERE id NOT IN (SELECT id FROM _keep) AND updated < ?",
                                  (now - paper_days * 86400,)).rowcount

        # 匿名访客：最后一次阅读超过 anon_days 天
        stale = [r[0] for r in c.execute(
            "SELECT user_id FROM history WHERE user_id != ? GROUP BY user_id HAVING MAX(last_read) < ?",
            (OWNER, now - anon_days * 86400))]
        for uid in stale:
            for t in ("history", "favorites", "favorite_folders", "folders", "chats", "dismissed", "rec_cache"):
                c.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
        out["visitors"] = len(stale)
        out["rec_cache"] = c.execute("DELETE FROM rec_cache WHERE created < ?", (now - rec_days * 86400,)).rowcount

        limit = fulltext_mb * 1024 * 1024
        total = c.execute("SELECT COALESCE(SUM(LENGTH(blocks)),0) FROM fulltext").fetchone()[0]
        removed = 0
        if total > limit:
            fav = {r[0] for r in c.execute("SELECT DISTINCT paper_id FROM favorites")}
            for pid, size in c.execute("SELECT paper_id, LENGTH(blocks) FROM fulltext ORDER BY created").fetchall():
                if total <= limit:
                    break
                if pid in fav:
                    continue
                c.execute("DELETE FROM fulltext WHERE paper_id=?", (pid,))
                total -= size
                removed += 1
        out["fulltext"] = removed
        c.commit()
        if sum(out.values()):
            c.execute("VACUUM")
    return out


def db_size_mb():
    return round(DB_FILE.stat().st_size / 1e6, 2) if DB_FILE.exists() else 0
