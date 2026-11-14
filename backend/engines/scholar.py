# -*- coding: utf-8 -*-
"""Google Scholar 检索。

Google Scholar 没有官方 API，直接抓网页会被验证码拦截，因此通过 SerpAPI 的 google_scholar
接口获取结构化结果（serpapi.com 免费额度 100 次/月）。未配置 key 时前端提供“在 Google Scholar 中打开”的跳转。
"""
import hashlib
import re

from .. import net

NAME = "Google Scholar"
API = "https://serpapi.com/search.json"
KEY_HINT = "Google Scholar 无官方 API，需在 serpapi.com 申请 key（免费 100 次/月）后到「设置」里填入"


def configured(cfg):
    return bool(cfg.get("serpapi_key"))


def to_paper(r):
    info = r.get("publication_info") or {}
    summary = info.get("summary") or ""
    # 形如 "A Author, B Author - IEEE Transactions on ..., 2023 - ieeexplore.ieee.org"
    parts = [s.strip() for s in summary.split(" - ")]
    authors = [a.get("name", "") for a in (info.get("authors") or [])]
    if not authors and parts:
        authors = [a.strip() for a in parts[0].split(",") if a.strip() and "…" not in a]
    venue, year = "", ""
    if len(parts) > 1:
        m = re.search(r"(19|20)\d{2}", parts[1])
        year = m.group(0) if m else ""
        venue = re.sub(r",?\s*(19|20)\d{2}.*$", "", parts[1]).strip(" ,…")
    host = parts[2] if len(parts) > 2 else ""
    pdf = ""
    for res in r.get("resources") or []:
        if (res.get("file_format") or "").upper() == "PDF":
            pdf = res.get("link", "")
            break
    link = r.get("link") or ""
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", link + " " + pdf)
    arxiv_id = m.group(1) if m else ""
    rid = r.get("result_id") or hashlib.md5((r.get("title") or "").encode()).hexdigest()[:12]
    text = f"{venue} {host}".lower()
    source = "IEEE" if "ieee" in text else ("arXiv" if arxiv_id else "Google Scholar")
    return {
        "id": f"scholar:{rid}",
        "arxiv_id": arxiv_id,
        "source": source,
        "title": re.sub(r"^\[[A-Z]+\]\s*", "", r.get("title") or "").strip(),
        "authors": authors[:15],
        "published": year,
        "abstract": (r.get("snippet") or "").strip(),
        "url": link,
        "pdf": pdf,
        "venue": venue,
        "citations": ((r.get("inline_links") or {}).get("cited_by") or {}).get("total"),
    }


def search(q, cfg, limit=20, sort="relevance", year_from=None):
    params = {"engine": "google_scholar", "q": q, "num": min(limit, 20), "api_key": cfg["serpapi_key"], "hl": "en"}
    if year_from:
        params["as_ylo"] = year_from
    if sort == "date":
        params["scisbd"] = 1
    data = net.get_json(API, params, timeout=30, retries=1)
    if data.get("error"):
        raise net.HTTPFail(data["error"])
    return [to_paper(r) for r in (data.get("organic_results") or []) if r.get("title")]
