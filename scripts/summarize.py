# -*- coding: utf-8 -*-
"""调用 `claude -p` 为 data/papers.json 中尚未总结的论文批量生成中文总结。"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data" / "papers.json"

PROMPT_TEMPLATE = """你是一位精通控制、自动驾驶、汽车动力学、机器人、无人机和人工智能的研究助理。
下面是若干篇论文的标题和摘要。请为每一篇生成中文总结。

严格输出一个 JSON 数组，不要输出任何其他文字、解释或 markdown 代码块。数组中每个元素格式为:
{{"id": "论文id", "tldr": "一句话中文概括(40字以内)", "points": ["要点1", "要点2", "要点3"], "tags": ["标签1", "标签2", "标签3"]}}

要求:
- tldr 直击论文核心贡献，不要空话
- points 为 2-4 条，涵盖: 解决什么问题、方法是什么、效果/结论如何
- tags 为 2-4 个简短中文技术标签(如 "模型预测控制"、"端到端"、"强化学习")
- id 必须与输入完全一致

论文列表:
{papers}"""


def build_batch_text(papers):
    parts = []
    for p in papers:
        abstract = (p.get("abstract") or "(无摘要，请根据标题推断)")[:1600]
        parts.append(f"---\nid: {p['id']}\n标题: {p['title']}\n摘要: {abstract}")
    return "\n".join(parts)


def parse_json_array(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("输出中未找到 JSON 数组")
    return json.loads(m.group(0))


def run_claude(prompt, claude_path):
    last_err = None
    for attempt in range(3):
        result = subprocess.run(
            [claude_path, "-p", "--model", CONFIG.get("claude_model", "haiku")],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.returncode == 0:
            return result.stdout
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        last_err = f"claude -p 失败 (exit {result.returncode}): {detail[:300]}"
        wait = 20 * (attempt + 1)
        print(f"    {last_err}，{wait}s 后重试...", flush=True)
        time.sleep(wait)
    raise RuntimeError(last_err)


def run_proxy(prompt):
    """通过本机 claude -p 的 Anthropic 兼容反代生成总结。"""
    base_url = os.environ.get("CLAUDE_PROXY_URL", CONFIG.get("claude_base_url", "http://127.0.0.1:8787"))
    base_url = base_url.rstrip("/")
    url = base_url + ("/messages" if base_url.endswith("/v1") else "/v1/messages")
    api_key = os.environ.get("CLAUDE_PROXY_KEY", CONFIG.get("claude_api_key", "unused"))
    body = json.dumps({
        "model": CONFIG.get("claude_model", "haiku"),
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }, ensure_ascii=False).encode("utf-8")

    last_err = None
    for attempt in range(3):
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = "".join(
                block.get("text", "") for block in payload.get("content", [])
                if block.get("type") == "text"
            )
            if not text:
                raise RuntimeError("反代返回内容为空")
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            last_err = f"反代返回 HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
            last_err = f"反代调用失败: {exc}"
        wait = 20 * (attempt + 1)
        print(f"    {last_err}，{wait}s 后重试...", flush=True)
        time.sleep(wait)
    raise RuntimeError(last_err)


def run_model(prompt, claude_path):
    backend = CONFIG.get("claude_backend", "proxy").lower()
    if backend == "proxy":
        return run_proxy(prompt)
    if backend == "cli":
        return run_claude(prompt, claude_path)
    raise RuntimeError(f"不支持的 claude_backend: {backend}")


def summarize_batch(papers, claude_path):
    prompt = PROMPT_TEMPLATE.format(papers=build_batch_text(papers))
    output = run_model(prompt, claude_path)
    items = parse_json_array(output)
    by_id = {it.get("id"): it for it in items if isinstance(it, dict)}
    done = 0
    for p in papers:
        it = by_id.get(p["id"])
        if it and it.get("tldr"):
            p["summary"] = {
                "tldr": str(it.get("tldr", "")).strip(),
                "points": [str(x).strip() for x in (it.get("points") or []) if str(x).strip()],
                "tags": [str(x).strip() for x in (it.get("tags") or []) if str(x).strip()][:4],
            }
            done += 1
    return done


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    backend = CONFIG.get("claude_backend", "proxy").lower()
    claude_path = shutil.which("claude") if backend == "cli" else None
    if backend == "cli" and not claude_path:
        sys.exit("找不到 claude CLI，请确认已安装并在 PATH 中")

    db = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    pending = [p for p in db["papers"] if not p.get("summary")]
    if limit:
        pending = pending[:limit]
    if not pending:
        print("所有论文均已总结，无需处理")
        return
    print(f"待总结论文: {len(pending)} 篇，后端: {backend}，模型: {CONFIG.get('claude_model', 'haiku')}")

    batch_size = CONFIG.get("summarize_batch_size", 8)
    total_done = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        print(f"  批次 {i // batch_size + 1}: {len(batch)} 篇...", end=" ", flush=True)
        try:
            done = summarize_batch(batch, claude_path)
            print(f"完成 {done} 篇")
            total_done += done
        except Exception as e:  # noqa: BLE001
            print(f"批量失败({e})，逐篇重试")
            for p in batch:
                try:
                    total_done += summarize_batch([p], claude_path)
                except Exception as e2:  # noqa: BLE001
                    print(f"    跳过 {p['id']}: {e2}")
        # 每批次后落盘，中断也不丢进度
        DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")

    remaining = len([p for p in db["papers"] if not p.get("summary")])
    print(f"本次总结 {total_done} 篇，库中仍待总结 {remaining} 篇")


if __name__ == "__main__":
    main()
