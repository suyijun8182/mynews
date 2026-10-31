# 我的新闻 MyNews

把 FreshRSS 里订阅的新闻，每天早晚各汇总一次，推送到 Telegram、企业微信、飞书、钉钉、邮件等 14 种渠道。
Morning and evening digests of your FreshRSS subscriptions, pushed to 14 channels.

源码与完整文档 / Source & docs：<https://github.com/suyijun8182/mynews>

## 快速开始

已有 MySQL：

```yaml
services:
  mynews:
    image: suyijun8182/mynews:latest
    container_name: mynews
    restart: unless-stopped
    ports:
      - "8844:8844/tcp"
    environment:
      TZ: Asia/Shanghai
      ADMIN_PASSWORD: ""
    volumes:
      - ./data:/app/data
```

`docker compose up -d` 后打开 `http://<本机IP>:8844`，安装向导依次是：填写 MySQL → 设置管理员 → 连接 FreshRSS → 选推送渠道。
还没有 MySQL：用仓库里的 `docker-compose.with-mysql.yml`（自带 MySQL 8.4）。

不想装 MySQL：用 Linux 一键安装（SQLite）：

```bash
curl -fsSL https://raw.githubusercontent.com/suyijun8182/mynews/main/install.sh | sudo bash
```

## 功能

- 早报 08:00 / 晚报 20:00（可改、可关），按「进入 FreshRSS 的时间」划窗口，每篇只推一次
- 按 FreshRSS 分类分组，每个分类最多 N 条，链接 / 标题去重，可只选部分分类
- 可选 AI「今日要点」：OpenAI 兼容接口（DeepSeek、通义千问、Kimi、Ollama）
- 14 种渠道，和 EasySub 一致；超长自动拆分，失败重试 3 次，网页上可重推
- 网页版：本期报纸式版面、历史期、推送记录、「查看全部」只读链接
- 只读 FreshRSS（API 密码），密钥加密存储；数据保留 10 天（可改）

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | 空 | 留空走安装向导；也可直接写 `mysql+pymysql://…` |
| `TZ` | `Asia/Shanghai` | 早晚报的时区 |
| `HTTP_PORT` | `8844` | Web 端口 |
| `ADMIN_PASSWORD` | 空 | 管理员 admin 的初始密码 |
| `SECRET_KEY` | 自动生成 | 登录签名和密钥加密 |

## 升级

```bash
docker compose pull && docker compose up -d
```

## What's new

- **0.1.1**: 修复新闻较多时立即推送出现 DataError；启动时自动扩大旧数据库的整期内容字段，无需手动执行 SQL。Fix large digest storage on MySQL; automatically migrate existing databases.

- **0.1.0**: 首个版本：FreshRSS 早晚报、按分类汇总与去重、可选 AI 今日要点、14 种推送渠道（自动排版拆分、失败重试）、网页版与「查看全部」只读链接、Docker（MySQL）与 Linux 一键安装（SQLite）。First release.

维护者：suyijun8182 与 Claude Code · MIT
