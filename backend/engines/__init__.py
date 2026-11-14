# -*- coding: utf-8 -*-
"""统一检索：并行调用各引擎，去重合并，用倒数排名融合 (RRF) 排序。

ResearchGate 没有公开 API 且禁止抓取，不作为检索引擎；前端为每篇论文提供 ResearchGate 跳转链接，
其收录的正式论文基本都能通过 OpenAlex / Semantic Scholar 检索到。
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import config, store
from . import arxiv, ieee, openalex, scholar, semantic_scholar

ENGINES = {
    "arxiv": arxiv,
    "s2": semantic_scholar,
    "openalex": openalex,
    "ieee": ieee,
    "scholar": scholar,
}


def engine_info():
    cfg = config.load()
    out = []
    for key, mod in ENGINES.items():
        out.append({
            "key": key,
            "name": mod.NAME,
            "configured": mod.configured(cfg),
            "hint": getattr(mod, "KEY_HINT", ""),
        })
    out.append({"key": "researchgate", "name": "ResearchGate", "configured": False, "link_only": True,
                "hint": "ResearchGate 无公开 API，提供逐篇跳转；其收录论文可经 OpenAlex / Semantic Scholar 检索"})
    return out


def _key(p):
    doi = store.norm_doi(p.get("doi"))
    return ("doi", doi) if doi else ("t", store.norm_title(p.get("title")))


def search(q, sources=None, limit=20, sort="relevance", year_from=None):
    cfg = config.load()
    sources = [s for s in (sources or cfg.get("default_sources") or ENGINES) if s in ENGINES]
    status = {}
    results = {}
    t0 = time.time()

    def run(key):
        mod = ENGINES[key]
        if not mod.configured(cfg):
            return key, None, getattr(mod, "KEY_HINT", "未配置")
        try:
            return key, mod.search(q, cfg, limit=limit, sort=sort, year_from=year_from), None
        except Exception as e:  # noqa: BLE001 - 单个引擎失败不影响整体
            return key, None, str(e)[:200]

    with ThreadPoolExecutor(max_workers=len(sources) or 1) as pool:
        futs = [pool.submit(run, s) for s in sources]
        for fut in as_completed(futs):
            key, papers, err = fut.result()
            if papers is None:
                status[key] = {"ok": False, "count": 0, "error": err,
                               "skipped": not ENGINES[key].configured(cfg)}
            else:
                status[key] = {"ok": True, "count": len(papers)}
                results[key] = papers

    # 合并 + RRF
    merged = {}
    scores = {}
    alias = {}
    for key, papers in results.items():
        for rank, p in enumerate(papers):
            k = _key(p)
            if k[1] == "":
                continue
            # 一个来源有 DOI、另一个没有时，按标题也认作同一篇
            tk = ("t", store.norm_title(p.get("title")))
            if k not in merged and len(tk[1]) > 12 and tk in alias:
                k = alias[tk]
            if len(tk[1]) > 12:
                alias.setdefault(tk, k)
            p = dict(p)
            p["found_in"] = [key]
            if k in merged:
                old = merged[k]
                # 多引擎重复命中：合并字段
                for fk, fv in p.items():
                    if fk == "found_in":
                        old["found_in"] = sorted(set(old["found_in"]) | {key})
                    elif fk == "abstract" and len(fv or "") > len(old.get("abstract") or ""):
                        old["abstract"] = fv
                    elif fv not in (None, "", []) and old.get(fk) in (None, "", []):
                        old[fk] = fv
            else:
                merged[k] = p
            scores[k] = scores.get(k, 0) + 1.0 / (60 + rank)

    items = list(merged.items())
    if sort == "date":
        items.sort(key=lambda kv: kv[1].get("published") or "", reverse=True)
    elif sort == "citations":
        items.sort(key=lambda kv: kv[1].get("citations") or 0, reverse=True)
    else:
        items.sort(key=lambda kv: scores[kv[0]], reverse=True)

    papers = []
    for _, p in items:
        hit = p["found_in"]
        saved = dict(store.stage_paper(p))
        saved["found_in"] = hit  # 只显示本次检索命中的来源
        papers.append(saved)
    return {"query": q, "results": papers, "status": status, "elapsed": round(time.time() - t0, 2)}
