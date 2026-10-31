<div align="center">

# 我的新闻 MyNews

**把 FreshRSS 里订阅的新闻，每天早晚各汇总一次，推送到 Telegram、企业微信、飞书、钉钉、邮件等 14 种渠道。**

[![License](https://img.shields.io/github/license/suyijun8182/mynews?color=blue)](./LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/suyijun8182/mynews?logo=docker)](https://hub.docker.com/r/suyijun8182/mynews)
[![Latest Version](https://img.shields.io/github/v/tag/suyijun8182/mynews?sort=semver&logo=github&label=version)](https://github.com/suyijun8182/mynews/releases)

**中文 | [English](#english)**

```bash
curl -fsSL https://raw.githubusercontent.com/suyijun8182/mynews/main/install.sh | sudo bash
```

</div>

---

## 功能

| | |
|---|---|
| **早报 / 晚报** | 默认 08:00 和 20:00 各推一期，时间可改、可单独关掉。早报覆盖前一天 20:00 到当天 08:00，晚报覆盖 08:00 到 20:00 |
| **按分类汇总** | 按 FreshRSS 分类归并相似报道，每类最多精选 8 件事，仅发送代表标题和阅读链接；可以只选部分分类 |
| **本地精选** | 综合来源覆盖、标题信息量和时效性排序，降低广告与重复转载的优先级；不调用 AI，不发送正文摘录 |
| **14 种推送渠道** | Telegram、飞书、QQ、Bark、邮件、Pushplus、Server酱、企业微信（群机器人 / 自建应用）、钉钉、Discord、Slack、ntfy、Gotify、Webhook，和 [EasySub](https://github.com/suyijun8182/easysub) 完全一致 |
| **自动排版与拆分** | Telegram、钉钉、Discord、Slack、企业微信 markdown 里标题是可点击的链接；超过渠道长度上限自动拆成几条并标「（2/3）」 |
| **不漏不重** | 每篇文章只推一次；按「进入 FreshRSS 的时间」划时间窗口，不怕源的发布时间不准；推送失败自动重试 3 次，网页上可以重推 |
| **网页版** | 本期报纸式版面、历史期翻看、推送记录；配置外部访问地址后，消息末尾附「查看全部」只读链接 |
| **只读、加密** | 只用 FreshRSS 的 API 密码读取文章，不改已读状态；API 密码、渠道密钥加密存储 |
| **两种部署** | Docker（MySQL，首次打开网页时填写连接信息）；Linux 一键安装（SQLite，网页上一键升级） |

各期内容、推送记录和文章缓存默认保留 10 天（可改），每天凌晨自动清理。

## 快速开始

### 方式一：Linux 一键安装（最省事）

```bash
curl -fsSL https://raw.githubusercontent.com/suyijun8182/mynews/main/install.sh | sudo bash
```

- 支持 x86_64 和 arm64；以专用账号 `mynews` 作为 systemd 服务运行。
- 数据库用内置的 **SQLite**（`/opt/mynews/data/mynews.db`），不用装 MySQL。
- 装好后打开 `http://<服务器IP>:8844`，按安装向导：设置管理员 → 连接 FreshRSS → 选推送渠道。
- 以后在网页 **设置 → 系统 → 版本** 里一键升级（下载后校验 SHA256，只重启服务，不重启系统），或者再执行一遍安装命令。
- 自定义配置写在 `/etc/mynews.env`，重装不会覆盖。

### 方式二：Docker（MySQL）

**已有 MySQL：**

```bash
curl -fsSLO https://raw.githubusercontent.com/suyijun8182/mynews/main/docker-compose.yml
docker compose up -d
```

打开 `http://<本机IP>:8844`，安装向导依次是：**填写 MySQL → 设置管理员 → 连接 FreshRSS → 选推送渠道**（最后一步可以跳过）。

**还没有 MySQL：** 用自带 MySQL 的版本，在同目录建一个 `.env` 写两个密码：

```bash
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/suyijun8182/mynews/main/docker-compose.with-mysql.yml
printf 'MYSQL_PASSWORD=改成强密码\nMYSQL_ROOT_PASSWORD=改成另一个强密码\n' > .env
docker compose up -d
```

连接串已经写好，安装向导会跳过数据库这一步。

### 准备 MySQL（已有 MySQL 时）

用管理员账号在 MySQL 里执行（把密码换掉）：

```sql
CREATE DATABASE mynews CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mynews'@'%' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON mynews.* TO 'mynews'@'%';
FLUSH PRIVILEGES;
```

- 账号有建库权限的话，库不存在时会自动创建，第一行可以省掉。
- MySQL 和本服务在同一台机器时，安装向导里的地址请填**局域网 IP**，不要填 `127.0.0.1`（容器里的 127.0.0.1 是容器自己）。
- 连接信息保存在 `./data/db_config.json`。要换数据库：删掉这个文件后重启容器，重新走向导。

## 连接 FreshRSS

本项目通过 FreshRSS 自带的 **Google Reader 兼容 API** 读取文章，用的是单独的 **API 密码**，不是你的登录密码：

1. 用管理员登录 FreshRSS，打开 **设置 → 认证**，勾选「允许 API 访问」。
2. 打开 **设置 → 账户 → API 管理**，设置一个 API 密码。
3. 在本项目的 **设置 → FreshRSS** 里填写 FreshRSS 地址（首页地址即可，例如 `https://rss.example.com:8443`）、用户名和 API 密码，点「测试连接」。

本项目**只读**：不会把文章标成已读，也不会改星标。已读、未读的文章都会汇总；推过的文章本地记下，不会重复推送。

## 早报和晚报

| | 默认时间 | 覆盖的文章（按进入 FreshRSS 的时间） |
|---|---|---|
| 早报 | 08:00 | 前一天 20:00 ～ 当天 08:00 |
| 晚报 | 20:00 | 当天 08:00 ～ 20:00 |
| 立即推送 | 点按钮时 | 上一期之后到现在（最多 24 小时） |

- 只开一个时，它覆盖过去 24 小时。时区由 `TZ` 决定（默认 `Asia/Shanghai`）。
- 服务在推送时间停了，1 小时内恢复会补发；同一期不会推两遍。
- 没有新文章时不推送，只在历史里记一笔。
- 每个类别最多精选 **8 件事**，不足不凑数；网页上的完整版保留全部报道。旧的每类条数设置不再影响推送。

推送消息的样子：

```
我的新闻 · 早报 · 10月29日 周四
共 42 篇报道，来自 8 个分类，精选 24 件事

【科技】
1. 代表事件标题
   阅读链接
……
查看全部 42 条 → https://你的地址/i/12?t=…
```

## 推送渠道

渠道、字段和 [EasySub](https://github.com/suyijun8182/easysub) 一致，在 **设置 → 推送渠道** 里配置，每个渠道都能用还没保存的配置发测试消息。

| 渠道 | 排版 | 单条上限（超过自动拆分） |
|---|---|---|
| Telegram | HTML，标题可点 | 约 3800 字 |
| 钉钉 | Markdown，标题可点 | 约 18000 字节 |
| 企业微信 | markdown 消息类型时标题可点；text 为纯文本 | markdown 3900 字节 / text 1900 字节 |
| Discord / Slack | Markdown / mrkdwn，标题可点 | 1800 / 3500 字 |
| 飞书、QQ、Bark、ntfy、Gotify、Pushplus、Server酱 | 纯文本 | 按各自上限 |
| 邮件、Webhook | 纯文本 | 不拆分 |

## 本地分类精选

每类最多 8 件事，只发送清理后的代表标题与阅读链接。网页版上方展示同一份精选，下方保留全部报道及原有摘要。

- 同链接、同标题或高度相似的标题归为同一事件；数字、主体或结果不同的报道保守地分开。规则不生成新事实，措辞差异较大的同一事件可能无法合并。
- 优先选择多来源覆盖、标题信息更充足且较新的事件；同站转载不增加来源覆盖权重，广告和空泛标题降低优先级。
- 来源覆盖按链接站点估算，不代表已核实媒体独立性；标题信息量采用字数等启发式指标，无法替代编辑判断。
- 全程在本地运行，不调用 AI；原来保存的 AI 配置不再自动使用。查看 **设置 → 分类精选** 可了解规则。
- 网页保留所选分类窗口内全部报道，包括同事件的不同报道。整期处理过的报道统一归入本期，不会在下一期重复积累。

## 「查看全部」链接

在 **设置 → 系统 → 外部访问地址** 填上能从手机打开的地址（例如反向代理后的 `https://news.example.com`），推送消息末尾就会附上这一期的只读链接：带随机令牌，不用登录，过了保留天数自动失效。不填就不附链接。

## 环境变量

FreshRSS、早晚报和渠道都在网页上配置。环境变量只有这些（完整说明见 [.env.example](./.env.example)）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | 空 | Docker 留空走安装向导；Linux 一键安装默认 SQLite。也可以直接写 MySQL / SQLite 连接串 |
| `TZ` | `Asia/Shanghai` | 早晚报按这个时区定时 |
| `HTTP_PORT` | `8844` | Web 端口 |
| `ADMIN_PASSWORD` | 空 | 管理员 `admin` 的初始密码；留空则在安装向导里设置 |
| `SECRET_KEY` | 自动生成 | 登录签名和密钥加密用；换掉后已保存的密钥要重新填写 |
| `DATA_DIR` | `./data` | 数据目录（数据库连接配置、SQLite 库） |

## 升级

- **Docker**：`docker compose pull && docker compose up -d`。有新版本时网页 **设置 → 系统** 会提示。
- **Linux**：网页 **设置 → 系统 → 版本 → 一键更新**；或者再执行一遍安装命令。

## 安全建议

- 安装向导完成之前，能打开网页的人都可以设置管理员。从**公网地址**打开向导需要填启动日志里的**安装码**（`docker logs mynews` 或 `journalctl -u mynews | grep 安装码`）；内网访问不需要。
- 要从外网访问，请放在 HTTPS 反向代理后面。
- 登录连续失败 5 次锁定 15 分钟。
- 网页上显示的密钥只露开头几位；改了发送地址就必须重新填写密钥，防止被套走。

## 开发

```bash
# 后端
cd backend && pip install -r requirements.txt pytest
python -m pytest -q tests
DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app --port 8844 --reload
# 前端（另开一个终端，/api 代理到 8844）
cd frontend && npm ci && npm run dev
```

设计规范见 [design-system/mynews/MASTER.md](./design-system/mynews/MASTER.md)。

## 维护者

[suyijun8182](https://github.com/suyijun8182) 与 Claude Code。

## 许可

[MIT](./LICENSE)

---

<a id="english"></a>

## English

**MyNews collects the articles from your FreshRSS subscriptions every morning and evening and pushes a digest to 14 channels: Telegram, WeCom, Feishu, DingTalk, email and more.**

### Features

- **Morning and evening issues** at 08:00 and 20:00 by default (editable, each can be turned off). The morning issue covers 20:00 the day before to 08:00; the evening issue covers 08:00 to 20:00.
- **Local category highlights**: similar reports are grouped into up to 8 events per category. Pushes contain representative headlines and links; all reports remain available on the web.
- **No AI calls**: events are ranked locally by publisher coverage, headline information and freshness. Ads and reposts receive lower priority. Conservative title matching can miss differently worded reports about the same event.
- **14 channels**, the same as [EasySub](https://github.com/suyijun8182/easysub). Titles are clickable links on Telegram, DingTalk, Discord, Slack and WeCom markdown. Long digests are split automatically.
- **Each article is sent once.** Windows are based on when articles entered FreshRSS. Failed sends are retried 3 times and can be re-sent from the web UI.
- **Web UI**: a newspaper-style page for the latest issue, browsing past issues, and delivery history. With a public URL set, messages end with a read-only "See all" link.
- **Read-only and encrypted.** MyNews uses the FreshRSS API password and never changes read state. Secrets are encrypted at rest.
- **Two deployments**: Docker with MySQL (entered in the setup wizard), or a one-line Linux install with SQLite and in-app updates.

### Quick start

```bash
# Linux (SQLite, systemd service)
curl -fsSL https://raw.githubusercontent.com/suyijun8182/mynews/main/install.sh | sudo bash

# Docker with your own MySQL
curl -fsSLO https://raw.githubusercontent.com/suyijun8182/mynews/main/docker-compose.yml && docker compose up -d
```

Open `http://<host>:8844` and follow the wizard: database (Docker only), then admin, then FreshRSS, then channels.
In FreshRSS, enable **Settings → Authentication → Allow API access** and set an API password under **Settings → Profile → API management**.

If you don't have MySQL yet, use `docker-compose.with-mysql.yml` with `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD` in a `.env` file.

### Upgrade

- **Docker**: `docker compose pull && docker compose up -d`.
- **Linux**: **Settings → System → Version → Update**, or run the install command again.

Maintained by [suyijun8182](https://github.com/suyijun8182) and Claude Code. MIT licensed.
