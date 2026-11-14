# 论文阅读 · Paper Reader

一个本地运行的 AI 论文阅读网站：多源学术检索、订阅最新论文、AI 精读解析、边读边问的伴读助手、个性化推荐、阅读记录与分类收藏。界面采用苹果式简约设计语言，支持深色模式和窄屏。

## 功能

| 模块 | 说明 |
|---|---|
| **多源检索** | 同时检索 arXiv、Semantic Scholar（覆盖 IEEE / Elsevier / Springer 等期刊会议）、OpenAlex、IEEE Xplore、Google Scholar；按 DOI / 标题去重合并，用倒数排名融合 (RRF) 排序，可按相关度 / 最新 / 引用数排序、按年份过滤 |
| **订阅最新论文** | 按 `config.json` 里的领域（控制、自动驾驶、汽车动力学、机器人、无人机、人工智能）定期抓取，并用 Claude 批量生成中文总结 |
| **阅读器** | 全文（优先 arXiv HTML 版，其次解析开放获取 PDF，保留章节结构和公式）/ PDF 原版 / 概览三种视图，带目录导航 |
| **AI 解读** | 读完全文后给出：一句话总结、论证主线、背景与问题、主要贡献、**架构脉络**（逐章节，点击跳到原文）、方法拆解、实验结论、**重点关注**（标注原文位置）、局限、延伸方向、术语表、前置知识、阅读建议 |
| **伴读对话** | 基于全文的流式对话，回答注明出处章节；选中原文任意段落可一键「解释 / 翻译 / 提问」；对话按论文保存 |
| **现场推荐** | 只用你读过 / 收藏 / 对话过的论文建兴趣画像（阅读时长、收藏、对话加权，30 天半衰期），提炼主题词组后**当场**检索 arXiv（按最新）、OpenAlex、Semantic Scholar 并调用 S2 多篇推荐接口，再加最近两周的订阅论文，一次一两百篇候选；只给这一批算相似度 + 新近度，MMR 去冗余，附推荐理由。结果缓存 3 小时，「换一批」当场重算（约 5–10 秒），站长的推荐每天早上随论文库更新提前算好。不需要常驻的全库索引 |
| **相关论文** | 阅读页里当场查：Semantic Scholar 推荐（限流时改用 OpenAlex 相关作品）+ 按这篇论文的主题词组检索的同主题论文 |
| **阅读记录** | 自动记录打开过的论文、阅读时长和次数，按天分组，带统计 |
| **收藏夹** | 多文件夹分类（一篇可放多个文件夹）、阅读状态（待读 / 在读 / 已读）、标签、笔记；收藏时按内容相似度推荐文件夹；可导出 BibTeX |

## 快速开始

```bash
pip install -r requirements.txt
```

```bash
python serve.py
```

然后打开 <http://localhost:8303>。第一次使用先设置站长密码：

```bash
python scripts/set_password.py
```

## 谁能用什么

| | 访客 | 站长（输入密码解锁） |
|---|---|---|
| 检索、阅读全文 / PDF、相关推荐、看已有的 AI 解读 | ✓ | ✓ |
| 阅读记录、收藏夹、个性化推荐 | ✓（按浏览器各自独立） | ✓（任何设备解锁后都是同一份） |
| AI 解读、伴读对话 | 填自己的 API 后可用 | ✓ 用站长的 AI |
| 更新论文库、服务器设置、重新生成解读 | — | ✓ |

- **站长的 AI**：默认走服务器上 Claude Code 的订阅（`claude -p`，算订阅额度，不花 API 的钱），模型 Claude Opus 5.5，effort medium。没装或没登录 Claude Code 时，改走「设置」里的 Anthropic 兼容接口（本机反代或 `https://api.anthropic.com`）；走 `api.anthropic.com` 时会带上服务端拒答自动换模型（`fallbacks: "default"`）。
- **访客自己的 API**：左下角「AI 设置 → 我自己的 API」，支持 Anthropic 和 OpenAI 兼容格式（DeepSeek、通义、Kimi 等）。Key 只存在访客浏览器里，每次请求带给服务器转发，服务器不保存、不写日志；地址必须是公网 https，不能指向内网。
- **密码**：只保存加盐哈希（PBKDF2，`config.local.json`）；同一 IP 15 分钟内错 5 次、全站 1 小时内错 30 次就暂停尝试。解锁状态在该设备保持 90 天，可在「AI 设置」里退出。
- **AI 解读是共享的**：同一篇论文解读一次，所有人都能看，不重复消耗额度；只有站长能重新生成。

## 数据源说明

| 数据源 | 需要 key | 说明 |
|---|---|---|
| arXiv | 否 | 官方 API |
| Semantic Scholar | 可选 | 免 key 时与他人共享限流，常见 429；[申请 key](https://www.semanticscholar.org/product/api#api-key-form) 后更稳定 |
| OpenAlex | 可选 | 免 key 有每日共享额度；[免费 key](https://openalex.org/settings/api) 额度更高 |
| IEEE Xplore | 是 | 在 [developer.ieee.org](https://developer.ieee.org/) 免费申请；未配置时 IEEE 论文仍可经 Semantic Scholar / OpenAlex 检索到 |
| Google Scholar | 是 | 没有官方 API，直接抓取会被验证码拦截，因此经 [SerpAPI](https://serpapi.com/) 获取（免费 100 次/月）；未配置时提供跳转链接 |
| ResearchGate | — | 没有公开 API 且禁止抓取，只提供逐篇 / 按关键词跳转；它收录的正式论文基本都能经 OpenAlex / Semantic Scholar 检索到 |

所有 key 都在网页「设置」里填写，保存在 `config.local.json`（已加入 .gitignore，不会提交）。也可用环境变量 `IEEE_API_KEY`、`SERPAPI_KEY`、`S2_API_KEY`、`OPENALEX_API_KEY`、`CLAUDE_PROXY_URL`、`CLAUDE_PROXY_KEY`。

## 配置 (config.json)

| 项 | 说明 |
|---|---|
| `days_back` | 订阅抓取最近多少天的论文（默认 30） |
| `max_per_field_arxiv` / `max_per_field_s2` | 每个领域每个来源的抓取上限 |
| `ai_backend` | 站长的 AI 怎么调用：`auto`（默认，有 Claude Code 订阅就用 `claude -p`，否则用 `claude_base_url`）/ `cli` / `proxy` |
| `ai_model` / `ai_effort` | AI 解读与伴读对话：默认 `claude-opus-5-5` / `medium` |
| `claude_model` | 订阅论文批量总结用的模型（默认 `haiku`） |
| `claude_base_url` / `claude_api_key` | 不走订阅时的 Anthropic 兼容接口 |
| `pdf_cache_mb` | PDF 缓存上限（默认 2048 MB，超出删最久没用的） |

**存储策略**：检索和推荐结果只放内存，有人打开、收藏、解读或对话时才写进数据库；每天备份时清理 60 天没用到的论文缓存、超过 500 MB 的全文缓存（收藏的保留）、过期推荐和半年没来过的访客数据。
| `ai_context_chars` | 送给 AI 的全文最大字符数（默认 100000） |
| `fields.*` | 订阅领域：arXiv 检索式、Semantic Scholar 关键词与期刊；加一个条目即可新增领域 |

## 命令行（可选）

```bash
python scripts/update.py
```

```bash
python scripts/fetch_papers.py uav robotics
```

```bash
python scripts/summarize.py 8
```

## 部署到服务器（自动）

和 NJJ 裁剪工厂同一套方法、同一台服务器。推送到 GitHub `main` 分支即自动部署（`.github/workflows/deploy.yml`）：

1. GitHub Actions 检查 Python 语法，把程序打包
2. 通过受限 SSH 钥匙传到服务器，执行 `/usr/local/bin/deploy-paper`（源码 `deploy/deploy-paper.sh`）：
   建 / 更新虚拟环境（依赖变了才装）→ **先备份数据库** → 替换程序 → 重启 → 健康检查

| 内容 | 位置 |
|---|---|
| 程序 | `/opt/apps/paper`（systemd 服务 `app-paper`，端口 4303，只监听 127.0.0.1） |
| 配置 | `/opt/apps/paper/.env`（`HOST`、`PORT`、`BACKUP_DIR`）、`/opt/apps/paper/config.local.json`（站长密码哈希、各种 key） |
| 数据 | `/opt/apps/paper/data`（`user.db` 个人数据、`papers.json` 论文库、`pdf/` 缓存） |
| 备份 | `/opt/apps/paper/backups`（gzip 压缩；每天 3:30 留最近 14 份 + 最近 8 周每周一份，部署前留 5 份；同时清理缓存；`app-paper-backup.timer`） |
| 每日更新论文库 | `app-paper-update.timer`，每天 6:00 抓新论文并用订阅（haiku）总结 |
| 反向代理 | nginx `paper.liyucheng.me` + certbot HTTPS（`deploy/nginx-paper.conf`，已关闭缓冲以支持流式对话） |

### 第一次部署（在服务器上做一次）

```bash
sudo apt install -y python3-venv
sudo mkdir -p /opt/apps/paper && sudo chown ubuntu:ubuntu /opt/apps/paper
```

1. 部署脚本：把 `deploy/deploy-paper.sh` 装到 `/usr/local/bin/deploy-paper`（`chmod +x`），并允许 ubuntu 免密重启服务：`/etc/sudoers.d/app-paper` 写 `ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart app-paper.service`
2. systemd：把 `deploy/` 下的 `app-paper.service`、`app-paper-update.*`、`app-paper-backup.*` 拷到 `/etc/systemd/system/`，然后 `sudo systemctl daemon-reload && sudo systemctl enable app-paper app-paper-update.timer app-paper-backup.timer`
3. 部署钥匙：本地生成一对新钥匙，公钥加到 `~ubuntu/.ssh/authorized_keys`，前面加限制 `command="/usr/local/bin/deploy-paper",no-port-forwarding,no-agent-forwarding,no-pty`；私钥和 `ssh-keyscan 151.80.60.57` 的结果分别存成 GitHub 仓库 Secrets `DEPLOY_SSH_KEY`、`DEPLOY_KNOWN_HOSTS`
4. 域名：DNS 加 `paper.liyucheng.me` 指向服务器；`deploy/nginx-paper.conf` 拷到 `/etc/nginx/sites-available/` 并链接到 `sites-enabled/`，`sudo nginx -t && sudo systemctl reload nginx && sudo certbot --nginx -d paper.liyucheng.me`
5. 推送一次（或在 Actions 里手动运行）完成首次部署，然后设置站长密码：`cd /opt/apps/paper && .venv/bin/python scripts/set_password.py`

服务器上的 Claude Code 和 NJJ 共用同一个 ubuntu 账号的登录（`claude auth status` 能看到 `loggedIn: true` 即可），不用再配置。

常用命令（在服务器上）：

```bash
sudo systemctl status app-paper
```

```bash
journalctl -u app-paper -n 100
```

```bash
sudo systemctl start app-paper-update
```

## 目录结构

```
serve.py                  HTTP 服务：静态页面 + JSON API + 对话 SSE + PDF 代理
backend/
  config.py               配置读取（config.json + config.local.json + 环境变量）
  auth.py                 访客匿名身份、站长密码解锁、限流
  store.py                SQLite：论文缓存、阅读记录、收藏夹、AI 解读与对话、全文缓存
  engines/                检索引擎：arxiv / semantic_scholar / openalex / ieee / scholar，__init__ 负责并行检索与融合
  fulltext.py             全文获取：arXiv HTML → PDF（PyMuPDF）→ 摘要兜底
  ai.py                   AI：本机 claude -p（订阅）/ Anthropic 兼容接口 / 访客自己的 API
  recommend.py            推荐算法
scripts/                  订阅抓取、批量总结、设置密码、备份
deploy/                   服务器部署：部署脚本、systemd、nginx
web/                      前端（原生 ES Modules，无需构建）
data/papers.json          订阅论文库
data/user.db              个人数据（不入库）
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/search?q=&sources=&sort=&year_from=` | 多源检索 |
| GET | `/api/feed?field=` | 订阅论文 |
| GET | `/api/paper?id=` | 论文详情 + 收藏 + 解读 + 对话 |
| GET | `/api/fulltext?id=` | 结构化全文 |
| GET | `/api/pdf?id=` | PDF（同源代理） |
| POST | `/api/analyze` | AI 结构化解读 |
| POST | `/api/chat` | 伴读对话（SSE 流式） |
| GET | `/api/recommend` · `/api/recommend/web` · `/api/similar?id=` | 推荐 |
| GET/POST | `/api/history*` · `/api/folders*` · `/api/favorites*` | 阅读记录与收藏 |
| GET | `/api/export/bibtex?folder=` | 导出 BibTeX |
