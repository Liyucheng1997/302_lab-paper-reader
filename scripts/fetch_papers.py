# -*- coding: utf-8 -*-
"""从 arXiv 和 Semantic Scholar (含 IEEE 期刊) 抓取各领域近期论文，合并进 data/papers.json。"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data" / "papers.json"

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
ATOM = "{http://www.w3.org/2005/Atom}"

UA = {"User-Agent": "PaperReader/1.0 (personal research reading site)"}


def http_get(url, retries=4, backoff=5):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001 - 429/网络错误统一重试
            last_err = e
            wait = backoff * (attempt + 1)
            print(f"    请求失败 ({e})，{wait}s 后重试...")
            time.sleep(wait)
    raise RuntimeError(f"请求最终失败: {url}\n{last_err}")


def norm_title(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def fetch_arxiv(field_key, field_cfg, cutoff):
    query = field_cfg["arxiv_query"]
    params = urllib.parse.urlencode({
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": CONFIG["max_per_field_arxiv"],
    })
    xml_text = http_get(f"{ARXIV_API}?{params}")
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        published = entry.findtext(f"{ATOM}published", "")[:10]
        if published and published < cutoff:
            continue
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/", 1)[-1]
        title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}title", "")).strip()
        abstract = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}summary", "")).strip()
        authors = [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")]
        pdf = ""
        for link in entry.findall(f"{ATOM}link"):
            if link.get("title") == "pdf":
                pdf = link.get("href", "")
        papers.append({
            "id": f"arxiv:{arxiv_id}",
            "field": field_key,
            "source": "arXiv",
            "title": title,
            "authors": authors,
            "published": published,
            "abstract": abstract,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": pdf,
            "venue": "arXiv",
        })
    return papers


def fetch_s2(field_key, field_cfg, cutoff):
    params = urllib.parse.urlencode({
        "query": field_cfg["s2_query"],
        "venue": field_cfg["s2_venues"],
        "sort": "publicationDate:desc",
        "publicationDateOrYear": f"{cutoff}:",
        "fields": "title,abstract,url,venue,publicationDate,authors,externalIds,openAccessPdf",
        "limit": CONFIG["max_per_field_s2"] * 3,
    })
    try:
        data = json.loads(http_get(f"{S2_API}?{params}"))
    except RuntimeError as e:
        print(f"    Semantic Scholar 拉取失败，跳过该来源: {e}")
        return []
    papers = []
    for item in (data.get("data") or [])[: CONFIG["max_per_field_s2"]]:
        if not item.get("title"):
            continue
        ext = item.get("externalIds") or {}
        doi = ext.get("DOI", "")
        venue = item.get("venue") or ""
        source = "IEEE" if "ieee" in venue.lower() else "期刊"
        pdf_info = item.get("openAccessPdf") or {}
        papers.append({
            "id": f"s2:{item.get('paperId')}",
            "field": field_key,
            "source": source,
            "title": item["title"].strip(),
            "authors": [a.get("name", "") for a in (item.get("authors") or [])][:12],
            "published": item.get("publicationDate") or "",
            "abstract": (item.get("abstract") or "").strip(),
            "url": f"https://doi.org/{doi}" if doi else (item.get("url") or ""),
            "pdf": pdf_info.get("url", ""),
            "venue": venue,
        })
    return papers


def main():
    only_fields = sys.argv[1:] or list(CONFIG["fields"].keys())
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CONFIG["days_back"])).strftime("%Y-%m-%d")
    print(f"抓取 {cutoff} 之后的论文，领域: {', '.join(only_fields)}")

    if DATA_FILE.exists():
        db = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        db = {"updated": "", "papers": []}
    existing = {p["id"] for p in db["papers"]}
    existing_titles = {norm_title(p["title"]) for p in db["papers"]}

    added = 0
    for key in only_fields:
        cfg = CONFIG["fields"][key]
        print(f"[{cfg['name']}]")
        batch = []
        try:
            batch += fetch_arxiv(key, cfg, cutoff)
        except Exception as e:  # noqa: BLE001
            print(f"    arXiv 拉取失败: {e}")
        time.sleep(3)  # arXiv API 礼貌间隔
        batch += fetch_s2(key, cfg, cutoff)
        time.sleep(2)

        new_count = 0
        for p in batch:
            nt = norm_title(p["title"])
            if p["id"] in existing or nt in existing_titles:
                continue
            existing.add(p["id"])
            existing_titles.add(nt)
            db["papers"].append(p)
            new_count += 1
        added += new_count
        print(f"    新增 {new_count} 篇")

    # 清理超过保留窗口两倍的旧论文，避免无限膨胀
    keep_cutoff = (datetime.now(timezone.utc) - timedelta(days=CONFIG["days_back"] * 3)).strftime("%Y-%m-%d")
    before = len(db["papers"])
    db["papers"] = [p for p in db["papers"] if (p.get("published") or "9999") >= keep_cutoff]
    removed = before - len(db["papers"])

    db["papers"].sort(key=lambda p: p.get("published") or "", reverse=True)
    db["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成: 新增 {added} 篇, 清理过期 {removed} 篇, 库中共 {len(db['papers'])} 篇")


if __name__ == "__main__":
    main()
