# -*- coding: utf-8 -*-
"""arXiv 检索引擎（官方 Atom API，免 key）。"""
import re
import xml.etree.ElementTree as ET

from .. import net

NAME = "arXiv"
API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def configured(cfg):
    return True


def strip_version(aid):
    return re.sub(r"v\d+$", "", aid)


def build_query(q):
    q = q.strip()
    if re.search(r"\b(all|ti|abs|au|cat|id):", q):
        return q  # 用户写了 arXiv 高级检索语法
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]+"', " ", q)
    terms = [f'all:"{p}"' for p in phrases]
    terms += [f"all:{w}" for w in re.findall(r"[\w\-]+", rest) if len(w) > 1]
    return " AND ".join(terms) or f"all:{q}"


def parse(xml_text):
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id", "").rsplit("/abs/", 1)[-1]
        if not raw_id:
            continue
        aid = strip_version(raw_id)
        title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}title", "")).strip()
        if not title or title.lower() == "error":
            continue
        cats = [c.get("term") for c in entry.findall(f"{ATOM}category") if c.get("term")]
        out.append({
            "id": f"arxiv:{aid}",
            "arxiv_id": aid,
            "source": "arXiv",
            "title": title,
            "authors": [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")],
            "published": entry.findtext(f"{ATOM}published", "")[:10],
            "abstract": re.sub(r"\s+", " ", entry.findtext(f"{ATOM}summary", "")).strip(),
            "url": f"https://arxiv.org/abs/{aid}",
            "pdf": f"https://arxiv.org/pdf/{aid}",
            "venue": entry.findtext(f"{ARXIV_NS}journal_ref") or "arXiv",
            "doi": entry.findtext(f"{ARXIV_NS}doi") or "",
            "categories": cats[:6],
        })
    return out


def search(q, cfg, limit=20, sort="relevance", year_from=None):
    params = {
        "search_query": build_query(q),
        "max_results": limit,
        "sortBy": "submittedDate" if sort == "date" else "relevance",
        "sortOrder": "descending",
    }
    papers = parse(net.get_text(API, params, timeout=25, retries=1))
    if year_from:
        papers = [p for p in papers if (p["published"] or "0")[:4] >= str(year_from)]
    return papers


def get(arxiv_id):
    papers = parse(net.get_text(API, {"id_list": strip_version(arxiv_id)}, timeout=20, retries=1))
    return papers[0] if papers else None
