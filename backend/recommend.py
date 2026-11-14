# -*- coding: utf-8 -*-
"""现场推荐：不维护全库索引，每次推荐时当场到各学术库找候选，再按兴趣画像排序。

1. 兴趣画像：只用你自己读过 / 收藏 / 对话过的论文（按阅读时长、收藏、对话加权，30 天半衰期），
   做 TF-IDF（一元 + 二元词组 + 中文标签；IDF 取自最近的订阅论文），提炼出主题词组。
2. 候选：用主题词组当场检索 arXiv（按最新提交）、OpenAlex、Semantic Scholar（按相关度），
   加上 Semantic Scholar 多篇推荐接口和最近两周的订阅论文，几路并行，一次一两百篇。
3. 排序：只给这一批候选算相似度 + 新近度，MMR 去冗余，每条给出推荐理由。
4. 结果按用户缓存 3 小时；推荐出来的论文只放内存，有人打开 / 收藏才入库。
"""
import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta

from . import config, store
from .engines import arxiv, openalex, semantic_scholar

STOP = set("""a an the of and or for to in on at by with from as is are was were be been being this that these those
it its into via we our us they their them than then there here such using use used based new novel approach approaches
method methods paper propose proposed proposes study results result show shows shown can also which while where when
not but both each more most other some any all over under between within without through toward towards about across
model models problem problems system systems framework analysis performance high low first two three one well however
paper's work present presents provide provides achieve achieves effective efficient significant significantly
demonstrate demonstrates experimental experiments experiment data various different large small number set task tasks
existing recent recently further many may might should could would has have had do does done make makes made non
specifically particular particularly improve improved improves improvement compared comparison state art outperforms
key main approach ieee arxiv et al etc ii iii iv""".split())

CACHE_TTL = 3 * 3600
_bg = {"mtime": None, "df": Counter(), "n": 1}
_bg_lock = threading.Lock()
_refreshing = {}
_ref_lock = threading.Lock()


# ================= 文本向量 =================

def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokenize(text):
    words = [_stem(w) for w in re.findall(r"[a-z][a-z0-9\-]{1,}", (text or "").lower())]
    words = [w.strip("-") for w in words if w not in STOP and len(w) > 2]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


def paper_tokens(p):
    toks = tokenize(p.get("title") or "") * 2 + tokenize(p.get("abstract") or "") + tokenize(p.get("s2_tldr") or "")
    for t in (p.get("summary") or {}).get("tags") or []:
        toks += [f"#{t}"] * 2
    return toks


def background():
    """IDF 背景语料：最近的订阅论文（最多 2000 篇），论文库变化时重算。"""
    mtime = store.FEED_FILE.stat().st_mtime if store.FEED_FILE.exists() else None
    with _bg_lock:
        if _bg["mtime"] != mtime:
            papers = store.load_feed().get("papers", [])[:2000]
            df = Counter()
            for p in papers:
                df.update(set(paper_tokens(p)))
            _bg.update(mtime=mtime, df=df, n=max(1, len(papers)))
        return _bg["df"], _bg["n"]


def idf(t, df, n):
    return math.log((1 + n) / (1 + df.get(t, 0))) + 1


def vec(p, df, n):
    tf = Counter(paper_tokens(p))
    v = {t: (1 + math.log(c)) * idf(t, df, n) for t, c in tf.items()}
    return _norm(v)


def _norm(v):
    s = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / s for t, x in v.items()}


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0) for t, x in a.items())


def _recency(p):
    d = (p.get("published") or "")[:10]
    try:
        dt = datetime.strptime(d, "%Y-%m-%d") if len(d) == 10 else datetime.strptime(d[:4] + "-07-01", "%Y-%m-%d")
    except ValueError:
        return 0.0
    return math.exp(-max(0, (datetime.now() - dt).days) / 180)


def _seen_keys(p):
    keys = {p["id"]}
    if p.get("doi"):
        keys.add("doi:" + store.norm_doi(p["doi"]))
    t = store.norm_title(p.get("title"))
    if len(t) > 12:
        keys.add("t:" + t)
    return keys


# ================= 兴趣画像 =================

def interest_weights(uid):
    """{paper_id: 权重}：阅读时长与次数、收藏、对话，30 天半衰期；不感兴趣为负。"""
    now = time.time()
    w = Counter()
    for pid, h in store.history_map(uid).items():
        decay = 0.5 ** ((now - (h["last_read"] or now)) / 86400 / 30)
        w[pid] += (1.0 + 0.6 * math.log1p((h["seconds"] or 0) / 60) + 0.3 * math.log1p(h["read_count"] or 1)) * decay
    for pid, fav in store.favorites_all(uid).items():
        w[pid] += 3.0 * (0.5 ** ((now - (fav["added"] or now)) / 86400 / 90))
    for pid, n in store.chat_counts(uid).items():
        w[pid] += 0.8 + min(2.0, 0.4 * n)
    for pid in store.dismissed_ids(uid):
        w[pid] -= 2.0
    return w


def profile(uid, max_seeds=80):
    """返回 (画像向量, 种子论文 {id: 论文}, 权重, 已看过的去重键)。"""
    df, n = background()
    weights = interest_weights(uid)
    top = [pid for pid, x in sorted(weights.items(), key=lambda kv: -kv[1]) if x > 0][:max_seeds]
    papers = store.get_papers(list(weights))
    prof = Counter()
    for pid, wt in weights.items():
        p = papers.get(pid)
        if not p or wt == 0:
            continue
        for t, x in vec(p, df, n).items():
            prof[t] += wt * x
    prof = _norm({t: x for t, x in prof.items() if x > 0}) if prof else {}
    seen = set()
    for p in papers.values():
        seen |= _seen_keys(p)
    return prof, {pid: papers[pid] for pid in top if pid in papers}, weights, seen


def _display_term(t):
    return t[1:] if t.startswith("#") else t


def interest_keywords(prof, k=14):
    out = []
    for t, _w in sorted(prof.items(), key=lambda kv: -kv[1]):
        d = _display_term(t)
        if any(d in o or o in d for o in out):
            continue
        out.append(d)
        if len(out) >= k:
            break
    return out


def topic_phrases(prof, k=3):
    """从画像里提炼几个英文主题词组，用来当场检索。相邻二元词组会接成三元（model predictive + predictive control）。"""
    bigrams = [t for t, _ in sorted(prof.items(), key=lambda kv: -kv[1]) if " " in t and not t.startswith("#")][:16]
    phrases = []
    used = set()
    for b in bigrams:
        if b in used:
            continue
        words = b.split()
        for other in bigrams:
            if len(words) >= 3:
                break
            if other in used or other == b:
                continue
            o = other.split()
            if o[0] == words[-1] and o[1] not in words:
                words.append(o[1])
                used.add(other)
            elif o[1] == words[0] and o[0] not in words:
                words.insert(0, o[0])
                used.add(other)
        used.add(b)
        phrase = " ".join(words)
        if not any(set(phrase.split()) <= set(p.split()) for p in phrases):
            phrases.append(phrase)
        if len(phrases) >= k:
            break
    if not phrases:  # 没有二元词组时退回高权重单词两两组合
        unis = [t for t, _ in sorted(prof.items(), key=lambda kv: -kv[1]) if " " not in t and not t.startswith("#")][:6]
        phrases = [" ".join(unis[i:i + 2]) for i in range(0, min(len(unis), 6), 2)]
    return phrases[:k]


# ================= 候选（当场检索） =================

def _candidates(phrases, seeds, cfg, timeout=18):
    """几路并行检索，返回 (候选列表, 各来源状态)。超时的来源直接跳过。"""
    year_from = datetime.now().year - 2
    jobs = {}
    pool = ThreadPoolExecutor(max_workers=8)
    if phrases:
        # arXiv：一个请求用 OR 合并几个词组，按最新提交排序（arXiv 要求不要并发请求）
        q = " OR ".join("(" + " AND ".join(f"all:{w}" for w in ph.split()) + ")" for ph in phrases)
        jobs["arXiv"] = pool.submit(arxiv.search, q, cfg, 60, "date")
        for i, ph in enumerate(phrases):
            jobs[f"OpenAlex·{i}"] = pool.submit(openalex.search, ph, cfg, 20, "relevance", year_from)
        jobs["Semantic Scholar"] = pool.submit(semantic_scholar.search, " ".join(phrases[:2]), cfg, 30, "relevance", year_from)
    s2_ids = [p["s2_id"] for p in seeds if p.get("s2_id")][:20]
    if s2_ids:
        jobs["S2 推荐"] = pool.submit(semantic_scholar.recommend_multi, s2_ids, [], cfg, 40)
    done, _ = wait(list(jobs.values()), timeout=timeout)
    pool.shutdown(wait=False, cancel_futures=True)
    out, status = [], {}
    for name, fut in jobs.items():
        key = name.split("·")[0]
        if fut not in done:
            status.setdefault(key, "超时")
            continue
        try:
            out += fut.result() or []
            status[key] = "ok"
        except Exception as e:  # noqa: BLE001
            if status.get(key) != "ok":
                status[key] = "限流" if "429" in str(e) else "失败"
    # 最近两周的订阅论文（本地，不花外部请求）
    cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    out += [p for p in store.load_feed().get("papers", []) if (p.get("published") or "") >= cutoff][:800]
    return out, status


def _dedupe(papers):
    seen, out = {}, []
    for p in papers:
        if not p.get("title"):
            continue
        keys = _seen_keys(p) - {p["id"]}
        hit = next((seen[k] for k in keys if k in seen), None) or seen.get(p["id"])
        if hit is not None:
            old = out[hit]
            if len(p.get("abstract") or "") > len(old.get("abstract") or ""):
                old["abstract"] = p["abstract"]
            for k, v in p.items():
                if v not in (None, "", []) and old.get(k) in (None, "", []):
                    old[k] = v
            continue
        idx = len(out)
        out.append(dict(p))
        for k in _seen_keys(p):
            seen[k] = idx
    return out


def _mmr(scored, vecs, k, lam=0.75):
    chosen, pool = [], dict(scored)
    while pool and len(chosen) < k:
        best, best_val = None, -1e9
        for i, rel in pool.items():
            red = max((cos(vecs[i], vecs[c]) for c in chosen), default=0.0)
            val = lam * rel - (1 - lam) * red
            if val > best_val:
                best, best_val = i, val
        chosen.append(best)
        pool.pop(best)
    return chosen


def _reason(v, prof, seed_vecs, seeds):
    terms = []
    for t, _ in sorted(((t, x * prof.get(t, 0)) for t, x in v.items() if t in prof), key=lambda kv: -kv[1]):
        d = _display_term(t)
        if not any(d in o or o in d for o in terms):
            terms.append(d)
        if len(terms) >= 3:
            break
    best, best_s = None, 0.0
    for sid, sv in seed_vecs.items():
        s = cos(v, sv)
        if s > best_s:
            best, best_s = sid, s
    r = {"terms": terms}
    if best and best_s > 0.12:
        r["similar_to"] = {"id": best, "title": seeds[best]["title"]}
    return r


# ================= 推荐入口 =================

def cold_start(k):
    papers = sorted(store.load_feed().get("papers", []), key=lambda p: (bool(p.get("summary")), p.get("published") or ""),
                    reverse=True)
    return [{"paper": p, "score": 0, "reason": {"terms": [], "cold": True}} for p in papers[:k]]


def compute(uid, k=18):
    cfg = config.load()
    prof, seeds, weights, seen = profile(uid)
    if not prof:
        return {"cold_start": True, "items": cold_start(k), "keywords": [], "phrases": [], "sources": {},
                "created": time.time()}
    phrases = topic_phrases(prof)
    cands, status = _candidates(phrases, list(seeds.values()), cfg)
    cands = [p for p in _dedupe(cands) if not (_seen_keys(p) & seen)]
    df, n = background()
    vecs = [vec(p, df, n) for p in cands]
    sims = [cos(prof, v) for v in vecs]
    top_sim = max(sims, default=0) or 1.0
    scored = {i: 0.8 * (s / top_sim) + 0.2 * _recency(cands[i]) for i, s in enumerate(sims) if s > 0.02}
    best = dict(sorted(scored.items(), key=lambda kv: -kv[1])[: k * 4])
    order = _mmr(best, vecs, k)
    seed_vecs = {pid: vec(p, df, n) for pid, p in list(seeds.items())[:30]}
    items = []
    for i in order:
        p = store.stage_paper(cands[i])  # 只放内存，点开 / 收藏才入库
        items.append({"paper": p, "score": round(best[i], 4), "reason": _reason(vecs[i], prof, seed_vecs, seeds)})
    return {"cold_start": False, "items": items, "keywords": interest_keywords(prof), "phrases": phrases,
            "sources": status, "candidates": len(cands), "created": time.time()}


def recommend(uid, refresh=False, k=18):
    """返回缓存的推荐（3 小时内）；refresh=True 或过期时当场重算。"""
    cached = store.rec_cache_get(uid)
    fresh = cached and time.time() - cached["created"] < CACHE_TTL
    if fresh and not refresh:
        data = cached["data"]
        store.stage_many([it["paper"] for it in data["items"]])  # 重启后内存清空，重新放回
        return data
    with _ref_lock:
        ev = _refreshing.get(uid)
        owner = ev is None
        if owner:
            ev = _refreshing[uid] = threading.Event()
    if not owner:  # 同一用户已在计算：等它算完
        ev.wait(40)
        c = store.rec_cache_get(uid)
        return c["data"] if c else compute(uid, k)
    try:
        data = compute(uid, k)
        store.rec_cache_set(uid, data)
        return data
    finally:
        with _ref_lock:
            _refreshing.pop(uid, None)
        ev.set()


# ================= 单篇论文的相关论文 =================

def similar(paper, k=10):
    """全网相关（S2 推荐 → OpenAlex 相关作品） + 按这篇论文的主题词组当场检索。"""
    cfg = config.load()
    df, n = background()
    v = vec(paper, df, n)
    out = {"web": {"provider": None, "items": [], "errors": []}, "keyword": []}
    pool = ThreadPoolExecutor(max_workers=4)
    f_s2 = pool.submit(semantic_scholar.recommend_for, paper, cfg, k)
    phrases = topic_phrases(v, k=2)
    f_kw = []
    if phrases:
        f_kw.append(pool.submit(arxiv.search, " OR ".join("(" + " AND ".join(f"all:{w}" for w in ph.split()) + ")"
                                                          for ph in phrases), cfg, 25, "relevance"))
        f_kw.append(pool.submit(openalex.search, phrases[0], cfg, 25, "relevance"))
    try:
        items = f_s2.result(timeout=20)
        if items:
            out["web"] = {"provider": "Semantic Scholar", "items": store.stage_many(items)}
    except Exception as e:  # noqa: BLE001
        out["web"]["errors"].append(f"Semantic Scholar: {e}")
    if not out["web"]["items"]:
        try:
            items = openalex.related(paper, cfg, limit=k)
            if items:
                out["web"] = {"provider": "OpenAlex", "items": store.stage_many(items)}
        except Exception as e:  # noqa: BLE001
            out["web"]["errors"].append(f"OpenAlex: {e}")
    cands = []
    for f in f_kw:
        try:
            cands += f.result(timeout=20)
        except Exception:  # noqa: BLE001
            pass
    pool.shutdown(wait=False, cancel_futures=True)
    me = _seen_keys(paper) | {k_ for p in out["web"]["items"] for k_ in _seen_keys(p)}
    cands = [p for p in _dedupe(cands) if not (_seen_keys(p) & me)]
    scored = sorted(((cos(v, vec(p, df, n)), p) for p in cands), key=lambda x: -x[0])
    out["keyword"] = [{"paper": store.stage_paper(p), "score": round(s, 4)} for s, p in scored[:k] if s > 0.05]
    out["phrases"] = phrases
    return out


def suggest_folder(uid, pid):
    """收藏时建议文件夹：与各文件夹已有论文的平均相似度最高者。"""
    paper = store.get_paper(pid)
    if not paper:
        return None
    df, n = background()
    v = vec(paper, df, n)
    favs = store.favorites_all(uid)
    papers = store.get_papers([x for x in favs if x != pid])
    by_folder = {}
    for fpid, fav in favs.items():
        if fpid in papers:
            for fid in fav["folder_ids"]:
                by_folder.setdefault(fid, []).append(vec(papers[fpid], df, n))
    best, best_s = None, 0.0
    for fid, vs in by_folder.items():
        sims = sorted((cos(v, o) for o in vs), reverse=True)[:5]
        s = sum(sims) / len(sims)
        if s > best_s:
            best, best_s = fid, s
    return {"folder_id": best, "score": round(best_s, 3)} if best and best_s > 0.08 else None
