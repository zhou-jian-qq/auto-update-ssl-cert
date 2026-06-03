# 行方 SSL 证书监控与下载管理后台

一个用于监控银行 HTTPS 接口服务端证书的轻量管理后台。系统通过 TLS 握手采集行方当前线上证书，解析有效期和指纹，临期或证书变化时发送企业微信/钉钉提醒，并提供候选 `.crt` 下载与人工确认。

## 快速启动

服务器部署推荐直接拉取 GitHub Actions 自动构建的镜像：

```bash
cp .env.example .env
# 编辑 .env，把 IMAGE 改成 ghcr.io/<github-owner>/<github-repo>:latest
docker compose pull
docker compose up -d
```

本地开发或临时打包：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

默认访问：

- 地址：http://localhost:8000
- 用户名：`admin`
- 密码：`admin123456`

生产环境请通过环境变量修改 `SECRET_KEY` 和 `ADMIN_PASSWORD`。

## GitHub 自动构建

仓库推送到 GitHub 后，`.github/workflows/docker.yml` 会自动执行：

1. 安装 Python 依赖并运行测试。
2. 构建 Docker 镜像。
3. 推送到 GitHub Container Registry，也就是 `ghcr.io/<github-owner>/<github-repo>`。

默认分支会生成 `latest` 标签，也会生成分支名和 `sha-xxxx` 标签。Linux 服务器部署时只需要配置：

```env
IMAGE=ghcr.io/<github-owner>/<github-repo>:latest
```

如果仓库是私有仓库，服务器需要先登录 GHCR：

```bash
echo <github-token> | docker login ghcr.io -u <github-username> --password-stdin
```

## 本地开发

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --reload
```

添加青岛银行示例配置：

```bash
python -m app.seed
```

## 关键配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8000` | Web 端口 |
| `SECRET_KEY` | `please-change-this-secret` | Session 密钥 |
| `ADMIN_USERNAME` | `admin` | 管理员用户名 |
| `ADMIN_PASSWORD` | `admin123456` | 管理员密码 |
| `CHECK_INTERVAL_MINUTES` | `720` | 定时检查间隔 |
| `WECHAT_WEBHOOK_URL` | 空 | 企业微信机器人 Webhook |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉机器人 Webhook |
| `NOTIFY_COOLDOWN_HOURS` | `24` | 同一告警限流时间 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 通知中的后台链接 |

## 说明

后台里的接口域名和端口用于连接行方 HTTPS 服务并采集证书，例如 `corporbank.qdccb.com:443`。如果银行官网证书下载页与业务接口域名不同，可以填到“官网证书页 URL”，仅作为人工参考。
