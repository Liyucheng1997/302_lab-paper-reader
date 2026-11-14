# -*- coding: utf-8 -*-
"""OpenAlex 检索（免费开放学术图谱，2.5 亿+ 作品，含 IEEE、ResearchGate 收录的大部分正式论文）。"""
import re

from .. import net

NAME = "OpenAlex"
API = "https://api.openalex.org"
SELECT = ("id,doi,display_name,publication_date,authorships,abstract_inverted_index,primary_location,"
          "best_oa_location,open_access,cited_by_count,locations,related_works")


def configured(cfg):
    return True


def _params(cfg, extra):
    p = dict(extra)
    if cfg.get("openalex_api_key"):
        p["api_key"] = cfg["openalex_api_key"]
    if cfg.get("openalex_mailto"):
        p["mailto"] = cfg["openalex_mailto"]
    return p


def rebuild_abstract(inv):
    if not inv:
        return ""
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    return " ".join(w for _, w in pos)


def to_paper(w):
    wid = (w.get("id") or "").rsplit("/", 1)[-1]
    doi = re.sub(r"^https?://doi\.org/", "", w.get("doi") or "")
    prim = w.get("primary_location") or {}
    src = prim.get("source") or {}
    venue = src.get("display_name") or ""
    publisher = src.get("host_organization_name") or ""
    best = w.get("best_oa_location") or {}
    pdf = best.get("pdf_url") or ""
    arxiv_id = ""
    for loc in w.get("locations") or []:
        url = (loc.get("landing_page_url") or "") + " " + (loc.get("pdf_url") or "")
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url)
        if m:
            arxiv_id = m.group(1)
            pdf = pdf or f"https://arxiv.org/pdf/{arxiv_id}"
            break
    text = f"{venue} {publisher}".lower()
    if "ieee" in text:
        source = "IEEE"
    elif "arxiv" in text:
        source = "arXiv"
    elif venue:
        source = "期刊"
    else:
        source = "OpenAlex"
    return {
        "id": f"openalex:{wid}",
        "openalex_id": wid,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "source": source,
        "title": re.sub(r"<[^>]+>", "", w.get("display_name") or "").strip(),
        "authors": [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])][:15],
        "published": w.get("publication_date") or "",
        "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
        "url": f"https://doi.org/{doi}" if doi else (prim.get("landing_page_url") or w.get("id") or ""),
        "pdf": pdf,
        "venue": venue,
        "publisher": publisher,
        "citations": w.get("cited_by_count"),
        "related_openalex": [r.rsplit("/", 1)[-1] for r in (w.get("related_works") or [])][:20],
    }


def search(q, cfg, limit=20, sort="relevance", year_from=None):
    params = {"search": q, "per-page": limit, "select": SELECT}
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    if sort == "date":
        params["sort"] = "publication_date:desc"
    data = net.get_json(f"{API}/works", _params(cfg, params), timeout=25, retries=1)
    return [to_paper(w) for w in (data.get("results") or []) if w.get("display_name")]


def lookup(paper, cfg):
    """按 DOI / OpenAlex id 查一篇作品。"""
    if paper.get("openalex_id"):
        key = paper["openalex_id"]
    elif paper.get("doi"):
        key = f"doi:{paper['doi']}"
    else:
        data = net.get_json(f"{API}/works", _params(cfg, {"search": paper["title"], "per-page": 1, "select": SELECT}),
                            timeout=20, retries=1)
        res = data.get("results") or []
        return to_paper(res[0]) if res else None
    w = net.get_json(f"{API}/works/{key}", _params(cfg, {"select": SELECT}), timeout=20, retries=1)
    return to_paper(w)


def related(paper, cfg, limit=12):
    """OpenAlex 的相关作品（S2 推荐不可用时的后备）。"""
    work = lookup(paper, cfg)
    if not work or not work.get("related_openalex"):
        return []
    ids = "|".join(work["related_openalex"][:limit])
    data = net.get_json(f"{API}/works", _params(cfg, {"filter": f"openalex_id:{ids}", "per-page": limit, "select": SELECT}),
                        timeout=25, retries=1)
    return [to_paper(w) for w in (data.get("results") or []) if w.get("display_name")]
