# -*- coding: utf-8 -*-
"""Semantic Scholar 检索 + 推荐（覆盖 IEEE / Elsevier / Springer 等正式发表论文）。"""
from .. import net

NAME = "Semantic Scholar"
GRAPH = "https://api.semanticscholar.org/graph/v1"
REC = "https://api.semanticscholar.org/recommendations/v1"
FIELDS = ("title,abstract,url,venue,publicationDate,year,authors,externalIds,"
          "openAccessPdf,citationCount,publicationVenue,tldr")
REC_FIELDS = "title,abstract,url,venue,publicationDate,year,authors,externalIds,openAccessPdf,citationCount,publicationVenue"


def configured(cfg):
    return True


def _headers(cfg):
    key = cfg.get("s2_api_key")
    return {"x-api-key": key} if key else {}


def classify_source(venue, publisher=""):
    text = f"{venue} {publisher}".lower()
    if "ieee" in text:
        return "IEEE"
    if "arxiv" in text and not publisher:
        return "arXiv"
    return "期刊" if venue else "Semantic Scholar"


def to_paper(item):
    ext = item.get("externalIds") or {}
    pv = item.get("publicationVenue") or {}
    venue = item.get("venue") or pv.get("name") or ""
    arxiv_id = ext.get("ArXiv") or ""
    doi = ext.get("DOI") or ""
    pdf = (item.get("openAccessPdf") or {}).get("url") or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "")
    source = classify_source(venue, pv.get("publisher") or "")
    if source in ("Semantic Scholar", "期刊") and arxiv_id and not doi:
        source = "arXiv"
    tldr = (item.get("tldr") or {}).get("text") or ""
    return {
        "id": f"s2:{item['paperId']}",
        "s2_id": item["paperId"],
        "arxiv_id": arxiv_id,
        "doi": doi,
        "source": source,
        "title": (item.get("title") or "").strip(),
        "authors": [a.get("name", "") for a in (item.get("authors") or [])][:15],
        "published": item.get("publicationDate") or (str(item["year"]) if item.get("year") else ""),
        "abstract": (item.get("abstract") or "").strip(),
        "s2_tldr": tldr,
        "url": f"https://doi.org/{doi}" if doi else (item.get("url") or ""),
        "pdf": pdf,
        "venue": venue,
        "citations": item.get("citationCount"),
    }


def search(q, cfg, limit=20, sort="relevance", year_from=None):
    params = {"query": q, "limit": limit, "fields": FIELDS}
    if year_from:
        params["year"] = f"{year_from}-"
    data = net.get_json(f"{GRAPH}/paper/search", params, _headers(cfg), timeout=20, retries=1)
    papers = [to_paper(it) for it in (data.get("data") or []) if it.get("title")]
    if sort == "date":
        papers.sort(key=lambda p: p["published"] or "", reverse=True)
    return papers


def external_id(paper):
    """把本地论文转成 S2 能识别的 id。"""
    if paper.get("s2_id"):
        return paper["s2_id"]
    if paper.get("arxiv_id"):
        return f"ARXIV:{paper['arxiv_id']}"
    if paper.get("doi"):
        return f"DOI:{paper['doi']}"
    return None


def recommend_for(paper, cfg, limit=12):
    pid = external_id(paper)
    if not pid:
        return []
    data = net.get_json(f"{REC}/papers/forpaper/{pid}",
                        {"fields": REC_FIELDS, "limit": limit, "from": "all-cs"},
                        _headers(cfg), timeout=25, retries=1)
    return [to_paper(it) for it in (data.get("recommendedPapers") or []) if it.get("title")]


def recommend_multi(positive, negative, cfg, limit=20):
    """基于多篇正/负样本论文推荐（用于“全网猜你喜欢”）。positive/negative 为 S2 paperId。"""
    data = net.post_json(f"{REC}/papers?fields={REC_FIELDS}&limit={limit}",
                         {"positivePaperIds": positive[:50], "negativePaperIds": negative[:50]},
                         _headers(cfg), timeout=30)
    return [to_paper(it) for it in (data.get("recommendedPapers") or []) if it.get("title")]


def resolve(paper, cfg):
    """查询论文在 S2 上的 paperId（用于多篇推荐）。"""
    pid = external_id(paper)
    if not pid:
        return None
    if paper.get("s2_id"):
        return paper["s2_id"]
    data = net.get_json(f"{GRAPH}/paper/{pid}", {"fields": "paperId"}, _headers(cfg), timeout=15, retries=1)
    return data.get("paperId")
