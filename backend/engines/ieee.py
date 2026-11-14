# -*- coding: utf-8 -*-
"""IEEE Xplore 官方 Metadata API（需要在 developer.ieee.org 免费申请 key）。"""
from .. import net

NAME = "IEEE Xplore"
API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
KEY_HINT = "在 developer.ieee.org 申请免费 API Key 后，到「设置」里填入即可启用"


def configured(cfg):
    return bool(cfg.get("ieee_api_key"))


def _date(a):
    year = str(a.get("publication_year") or "")
    return year


def to_paper(a):
    num = str(a.get("article_number") or "")
    authors = [x.get("full_name", "") for x in ((a.get("authors") or {}).get("authors") or [])]
    return {
        "id": f"ieee:{num}",
        "ieee_id": num,
        "doi": a.get("doi") or "",
        "source": "IEEE",
        "title": (a.get("title") or "").strip(),
        "authors": authors[:15],
        "published": _date(a),
        "abstract": (a.get("abstract") or "").strip(),
        "url": a.get("html_url") or f"https://ieeexplore.ieee.org/document/{num}",
        "pdf": "",  # IEEE PDF 需机构订阅，不做代理下载
        "venue": a.get("publication_title") or "",
        "citations": a.get("citing_paper_count"),
    }


def search(q, cfg, limit=20, sort="relevance", year_from=None):
    params = {
        "querytext": q,
        "max_records": limit,
        "apikey": cfg["ieee_api_key"],
        "format": "json",
    }
    if year_from:
        params["start_year"] = year_from
    if sort == "date":
        params["sort_field"] = "publication_year"
        params["sort_order"] = "desc"
    data = net.get_json(API, params, timeout=25, retries=1)
    return [to_paper(a) for a in (data.get("articles") or []) if a.get("title")]
