# 领域论文阅读

追踪 **控制、自动驾驶、汽车动力学、机器人、无人机、人工智能** 六个方向的近期论文，
用 `claude -p` 自动生成中文总结，并在本地网站上浏览。

## 数据来源

- **arXiv API** — 各领域预印本（按提交时间取最新）
- **Semantic Scholar API** — 覆盖 IEEE Transactions / RA-L / Automatica 等期刊会议的正式发表论文

## 使用方法

一键更新（抓取 + 总结）：

```bash
python scripts/update.py
```

启动网站：

```bash
python -m http.server 8303
```

然后打开 <http://localhost:8303>。

### 分步运行

```bash
# 只抓取（可指定领域: control / autonomous_driving / vehicle_dynamics / robotics / uav / ai）
python scripts/fetch_papers.py
python scripts/fetch_papers.py uav robotics

# 只总结（可限制篇数，便于测试）
python scripts/summarize.py
python scripts/summarize.py 8
```

## 配置 (config.json)

| 项 | 说明 |
|---|---|
| `days_back` | 抓取最近多少天的论文（默认 30；超过 3 倍窗口的旧论文自动清理） |
| `max_per_field_arxiv` / `max_per_field_s2` | 每个领域每个来源的抓取上限 |
| `claude_model` | 总结用的模型（默认 `haiku`，可改 `sonnet` / `opus` 提高质量） |
| `summarize_batch_size` | 每次 `claude -p` 调用总结几篇（默认 8） |
| `fields.*.arxiv_query` | arXiv 检索式（分类 `cat:` 或关键词 `all:`） |
| `fields.*.s2_query` / `s2_venues` | Semantic Scholar 关键词与期刊过滤（逗号分隔） |

想加新领域：在 `fields` 里加一个条目即可，网站标签自动生成。

## 目录结构

```
config.json            领域与抓取配置
scripts/fetch_papers.py  抓取 + 去重 + 清理过期
scripts/summarize.py     调用 claude -p 批量中文总结（每批落盘，可中断续跑）
scripts/update.py        一键: 抓取 + 总结
data/papers.json         论文库（含总结）
index.html / app.js / style.css  网站前端
```

## 说明

- 总结基于标题 + 摘要生成，仅供快速筛选，精读请看原文。
- Semantic Scholar 免费接口偶尔返回 429，脚本会自动退避重试。
- IEEE Xplore 官方 API 需要申请 key；当前通过 Semantic Scholar 覆盖 IEEE 论文，效果等价且免 key。
