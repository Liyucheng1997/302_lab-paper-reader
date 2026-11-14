# -*- coding: utf-8 -*-
"""全文获取与结构化：arXiv HTML 版 → PDF（PyMuPDF / pypdf 解析）→ 摘要兜底。

结果为 blocks 列表: {"t": "h", "lv": 1-3, "x": 标题} / {"t": "p", "x": 段落} / {"t": "page", "n": 页码}
"""
import hashlib
import re
from html.parser import HTMLParser

from . import config, net, store

PDF_DIR = config.DATA_DIR / "pdf"


# ---------------- arXiv HTML ----------------

class _ArxivHTML(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "button", "svg", "figure", "table"}
    HEAD = {"h1": 1, "h2": 1, "h3": 2, "h4": 3, "h5": 3, "h6": 3}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buf = []
        self.mode = None  # "h" / "p"
        self.level = 0
        self.skip = 0
        self._skip_tag = None
        self.math = 0
        self.in_abstract = False
        self.cites = 0

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if text and self.mode == "h":
            text = re.sub(r"^(\d+(\.\d+)*)\s*", r"\1 ", text)
            self.blocks.append({"t": "h", "lv": self.level, "x": text[:200]})
        elif text and self.mode == "p" and len(text) > 1:
            self.blocks.append({"t": "p", "x": text})
        self.mode = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        classes = set(cls.split())
        if self.skip:
            if tag == self._skip_tag:
                self.skip += 1
            return
        if tag in self.SKIP or any(k in classes for k in ("ltx_bibliography", "ltx_authors", "ltx_page_footer",
                                                         "ltx_role_footnote", "ltx_note", "ltx_tag_note")):
            if tag in ("br", "img", "hr", "input", "meta", "link"):
                return
            self.skip = 1
            self._skip_tag = tag
            return
        if tag == "math":
            alt = a.get("alttext") or ""
            if alt:
                self.buf.append(f" ${alt}$ ")
            self.math += 1
            return
        if tag in self.HEAD:
            self._flush()
            self.mode, self.level = "h", self.HEAD[tag]
        elif tag in ("p", "li") or (tag == "div" and "ltx_para" in cls and self.mode is None):
            if self.mode != "h":
                self._flush()
                self.mode = "p"
        elif tag == "br":
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self._skip_tag:
                self.skip -= 1
            return
        if tag == "math":
            self.math = max(0, self.math - 1)
            return
        if tag in self.HEAD or tag in ("p", "li"):
            self._flush()

    def handle_data(self, data):
        if self.skip or self.math:
            return
        if self.mode is None:
            if data.strip():
                self.mode = "p"
            else:
                return
        self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def from_arxiv_html(arxiv_id):
    html = net.get_text(f"https://arxiv.org/html/{arxiv_id}", timeout=30, retries=1)
    if "ltx_document" not in html and "ltx_page_main" not in html:
        return None
    parser = _ArxivHTML()
    parser.feed(html)
    parser.close()
    blocks = [b for b in parser.blocks if not (b["t"] == "p" and len(b["x"]) < 3)]
    # 去掉标题前的杂项（作者、机构等）
    for i, b in enumerate(blocks):
        if b["t"] == "h" and re.search(r"abstract|introduction", b["x"], re.I):
            blocks = blocks[i:]
            break
    text_len = sum(len(b.get("x", "")) for b in blocks)
    return blocks if text_len > 3000 else None


# ---------------- PDF ----------------

def pdf_path(paper):
    url = paper_pdf_url(paper)
    if not url:
        return None
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    name = hashlib.md5(url.encode()).hexdigest()[:16] + ".pdf"
    path = PDF_DIR / name
    if path.exists() and path.stat().st_size > 1000:
        path.touch()  # 记录最近使用，清理时保留常用的
        return path
    body, ctype = net.request(url, headers={"Accept": "application/pdf,*/*"}, timeout=60, retries=1)
    if not body.startswith(b"%PDF"):
        raise net.HTTPFail("PDF 链接返回的不是 PDF（可能需要机构登录）")
    if len(body) > 80 * 1024 * 1024:
        raise net.HTTPFail("PDF 太大（超过 80 MB）")
    path.write_bytes(body)
    prune_pdf_cache()
    return path


def prune_pdf_cache():
    """PDF 缓存超过上限（config pdf_cache_mb，默认 2048）时删掉最久没用的。"""
    limit = int(config.load().get("pdf_cache_mb") or 2048) * 1024 * 1024
    files = sorted(PDF_DIR.glob("*.pdf"), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= limit:
            break
        total -= f.stat().st_size
        try:
            f.unlink()
        except OSError:
            pass


def paper_pdf_url(paper):
    if paper.get("arxiv_id"):
        return f"https://arxiv.org/pdf/{paper['arxiv_id']}"
    return paper.get("pdf") or ""


HEADING_RE = re.compile(r"^((\d{1,2}(\.\d{1,2}){0,2})|([IVX]{1,5})|([A-H]))[\.\s]\s*[A-Z][A-Za-z\-–:,\s]{2,80}$")


def from_pdf(path):
    blocks = []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None
    if fitz:
        doc = fitz.open(str(path))
        toc_titles = {store.norm_title(t[1]): t[0] for t in doc.get_toc() if t[1]}
        for pno, page in enumerate(doc, 1):
            blocks.append({"t": "page", "n": pno})
            for b in page.get_text("blocks"):
                if b[6] != 0:  # 非文本块
                    continue
                text = b[4].strip()
                if not text:
                    continue
                text = re.sub(r"-\n(?=[a-z])", "", text)
                text = re.sub(r"\s*\n\s*", " ", text).strip()
                nt = store.norm_title(re.sub(r"^[\dIVX\.]+\s*", "", text))
                if nt and nt in toc_titles and len(text) < 120:
                    blocks.append({"t": "h", "lv": min(3, toc_titles[nt]), "x": text})
                elif len(text) < 90 and HEADING_RE.match(text):
                    lv = 2 if re.match(r"^\d+\.\d+", text) or re.match(r"^[A-H]\.", text) else 1
                    blocks.append({"t": "h", "lv": lv, "x": text})
                elif re.fullmatch(r"\d{1,4}", text):
                    continue  # 页码
                else:
                    blocks.append({"t": "p", "x": text})
        doc.close()
    else:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        for pno, page in enumerate(reader.pages, 1):
            blocks.append({"t": "page", "n": pno})
            for para in re.split(r"\n\s*\n", page.extract_text() or ""):
                para = re.sub(r"\s*\n\s*", " ", para).strip()
                if para:
                    blocks.append({"t": "p", "x": para})
    # 去掉第一页摘要之前的标题、作者、机构（页眉已展示）
    for i, b in enumerate(blocks[:40]):
        if b["t"] == "page" and b["n"] > 1:
            break
        if b["t"] in ("h", "p") and re.match(r"^(abstract|a b s t r a c t)", b["x"].strip(), re.I):
            blocks = [blocks[0]] + blocks[i:]
            break
    # 截断参考文献
    for i, b in enumerate(blocks):
        if b["t"] in ("h", "p") and re.fullmatch(r"(\d+\.?\s*)?(references|bibliography)", b["x"].strip(), re.I):
            if i > len(blocks) * 0.4:
                blocks = blocks[:i]
            break
    return blocks


# ---------------- 入口 ----------------

def get(paper, force=False):
    pid = paper["id"]
    if not force:
        cached = store.fulltext_get(pid)
        if cached:
            return cached
    errors = []
    blocks, source = None, None
    if paper.get("arxiv_id"):
        try:
            blocks = from_arxiv_html(paper["arxiv_id"])
            source = "arxiv-html" if blocks else None
        except Exception as e:  # noqa: BLE001
            errors.append(f"arXiv HTML: {e}")
    if not blocks and paper_pdf_url(paper):
        try:
            path = pdf_path(paper)
            blocks = from_pdf(path)
            source = "pdf" if blocks else None
        except Exception as e:  # noqa: BLE001
            errors.append(f"PDF: {e}")
    if blocks:
        store.fulltext_set(pid, source, blocks)
        return {"source": source, "blocks": blocks}
    # 兜底：只有摘要（不缓存，下次还会再尝试）
    blocks = [{"t": "h", "lv": 1, "x": "Abstract"}, {"t": "p", "x": paper.get("abstract") or "（无摘要）"}]
    return {"source": "abstract", "blocks": blocks, "errors": errors}


def as_text(ft, limit):
    parts = []
    for b in ft["blocks"]:
        if b["t"] == "h":
            parts.append("\n" + "#" * (b.get("lv", 1) + 1) + " " + b["x"])
        elif b["t"] == "p":
            parts.append(b["x"])
        elif b["t"] == "page":
            parts.append(f"[第 {b['n']} 页]")
    text = "\n".join(parts)
    if len(text) > limit:
        text = text[:limit] + "\n\n[……全文过长，后续内容已截断]"
    return text
