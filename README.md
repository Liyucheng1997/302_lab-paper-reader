# 领域论文阅读

追踪 **控制、自动驾驶、汽车动力学、机器人、无人机、人工智能** 六个方向的近期论文，
通过本机 `claude -p` 反代自动生成中文总结，并在本地网站上浏览。

## 数据来源

- **arXiv API** — 各领域预印本（按提交时间取最新）
- **Semantic Scholar API** — 覆盖 IEEE Transactions / RA-L / Automatica 等期刊会议的正式发表论文

## 使用方法

启动网站（带更新 API 的服务器）：

```bash
python serve.py
```

然后打开 <http://localhost:8303>。**点击页面右上角「🔄 更新」按钮**即可随时抓取新论文并生成总结
（可选「抓取 + 总结」/「仅抓取」/「仅总结」），进度日志实时显示在页面上，完成后列表自动刷新。
更新任务在服务器后台运行，关掉页面也不会中断。

### 命令行方式（可选）

```bash
# 一键更新（抓取 + 总结）
python scripts/update.py


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
| `claude_backend` | `proxy`（默认，调用本机反代）或 `cli`（直接启动 `claude -p`） |
| `claude_base_url` | 反代地址，默认 `http://127.0.0.1:8787`；也可用环境变量 `CLAUDE_PROXY_URL` 覆盖 |
| `claude_api_key` | 反代未启用鉴权时填 `unused`；也可用环境变量 `CLAUDE_PROXY_KEY` 覆盖 |
| `claude_model` | 总结用的模型（默认 `haiku`，可改 `sonnet` / `opus` 提高质量） |
| `summarize_batch_size` | 每次 `claude -p` 调用总结几篇（默认 8） |
| `fields.*.arxiv_query` | arXiv 检索式（分类 `cat:` 或关键词 `all:`） |
| `fields.*.s2_query` / `s2_venues` | Semantic Scholar 关键词与期刊过滤（逗号分隔） |

想加新领域：在 `fields` 里加一个条目即可，网站标签自动生成。

## 目录结构

```
serve.py               网站服务器: 静态页面 + POST /api/update + GET /api/status
config.json            领域与抓取配置
scripts/fetch_papers.py  抓取 + 去重 + 清理过期
scripts/summarize.py     调用 claude -p 反代或 CLI 批量中文总结（每批落盘，可中断续跑，限流自动重试）
scripts/update.py        命令行一键: 抓取 + 总结
data/papers.json         论文库（含总结）
index.html / app.js / style.css  网站前端
```

## 说明

- 总结基于标题 + 摘要生成，仅供快速筛选，精读请看原文。
- Semantic Scholar 免费接口偶尔返回 429，脚本会自动退避重试。
- IEEE Xplore 官方 API 需要申请 key；当前通过 Semantic Scholar 覆盖 IEEE 论文，效果等价且免 key。
