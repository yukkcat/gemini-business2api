# gemini-refresh-worker

独立部署的 Gemini Business 账户刷新服务。
Standalone refresh service for Gemini Business accounts.

它专注做一件事：从云端/数据库读取账号和刷新配置，检测即将过期的账号，并通过本机浏览器自动化刷新凭证。
It focuses on one job: load accounts and refresh settings from cloud/storage, detect accounts close to expiration, and refresh credentials through local browser automation.

## 先用交互脚本 / Start With The Interactive CLI

最推荐从交互脚本开始，它会引导你写入远程连接配置，并提供诊断、手动刷新、手动注册和前台轮询入口。
The recommended entrypoint is the interactive CLI. It can write remote bootstrap config and run diagnostics, manual refresh, registration, and foreground polling.

```bash
pip install -r requirements.txt
python -m worker.cli
```

如果只想配置 `.env`，可以直接跑向导：
If you only want to configure `.env`, run the wizard directly:

```bash
python -m worker.cli wizard
```

配置后建议先跑一次诊断：
After setup, run diagnostics first:

```bash
python -m worker.cli doctor
```

## 推荐部署方式 / Recommended Topology

- 远程部署一套主项目或 `beta`，负责管理后台和 API。
  Deploy one remote main/beta service for the admin panel and APIs.
- 本地或 Linux 服务器运行 `refresh-worker`，负责真实浏览器自动化。
  Run `refresh-worker` locally or on a Linux server for real browser automation.
- 业务配置统一在云端管理后台维护，本地 `.env` 只放启动连接信息。
  Business settings are managed in the cloud admin panel; local `.env` only stores bootstrap connection settings.

## 快速开始 / Quick Start

### 1) 选择存储模式 / Choose Storage Mode

推荐远程项目模式：worker 通过远端管理接口读写账号和配置。
Remote project mode is recommended: the worker reads/writes accounts and settings through remote admin APIs.

```env
REMOTE_PROJECT_BASE_URL=https://your-beta-domain.example
REMOTE_PROJECT_PASSWORD=your_admin_key
REMOTE_PROJECT_VERIFY_SSL=true
REMOTE_PROJECT_TIMEOUT_SECONDS=30
```

也可以直连数据库：
Direct database mode is also supported:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

如果同时配置 `DATABASE_URL` 和 `REMOTE_PROJECT_BASE_URL`，优先使用远程项目模式。
If both `DATABASE_URL` and `REMOTE_PROJECT_BASE_URL` are configured, remote project mode wins.

### 2) 启动 Worker / Run The Worker

```bash
python -m worker.main
```

前台轮询调试可以用：
For foreground polling/debugging:

```bash
python -m worker.cli poll
```

Docker Compose：

```bash
docker compose up -d --build
```

Docker 镜像：

```bash
docker run -d \
  --name gemini-refresh-worker \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  your_dockerhub_username/gemini-refresh-worker:latest
```

## 常用命令 / Common Commands

| 命令 / Command | 用途 / Purpose |
|---|---|
| `python -m worker.cli` | 打开交互菜单 / Open interactive menu |
| `python -m worker.cli wizard` | 写入远程启动配置 / Write remote bootstrap config |
| `python -m worker.cli doctor` | 检查配置、远程连接和 Google 连通性 / Check config, remote connection, and Google connectivity |
| `python -m worker.cli google` | 仅做 Google/代理诊断 / Run Google/proxy diagnostics only |
| `python -m worker.cli once` | 立即执行一轮刷新 / Run one refresh immediately |
| `python -m worker.cli poll` | 前台守护轮询 / Start foreground polling |
| `python -m worker.cli register --count 20 --provider duckmail` | 手动注册账号 / Register accounts manually |
| `python -m worker.cli lang en --save` | 切换并保存 CLI 语言 / Switch and persist CLI language |

## 配置原则 / Configuration Model

### `.env` 只做启动配置 / `.env` Is Bootstrap Only

本地环境变量只负责让 worker 启动并连接到云端或数据库：
Local environment variables only let the worker boot and connect to cloud/storage:

| 变量 / Variable | 说明 / Description |
|---|---|
| `REMOTE_PROJECT_BASE_URL` | 远程项目地址 / Remote project base URL |
| `REMOTE_PROJECT_PASSWORD` | 远程管理密码或 `ADMIN_KEY` / Remote admin password or `ADMIN_KEY` |
| `REMOTE_PROJECT_VERIFY_SSL` | 是否校验远程 HTTPS 证书 / Verify remote HTTPS certificate |
| `REMOTE_PROJECT_TIMEOUT_SECONDS` | 远程 API 超时时间 / Remote API timeout seconds |
| `DATABASE_URL` | 直连数据库模式连接串 / Direct database URL |
| `LOG_LEVEL` | 日志级别 / Log level |
| `HEALTH_PORT` | 健康检查端口，`0` 表示关闭 / Health port, `0` disables it |
| `CLI_LANG` | CLI 语言，`zh` 或 `en` / CLI language, `zh` or `en` |

### 业务配置全部走云端 / Business Settings Come From Cloud

这些配置不再读取本地环境变量：
These settings are no longer read from local environment variables:

- 定时刷新开关、刷新窗口、刷新批次和冷却时间
  Scheduled refresh, refresh window, batch size, and cooldown
- 浏览器模式、认证代理 `proxy_for_auth`
  Browser mode and auth proxy `proxy_for_auth`
- 自动删除过期账号、自动补充注册账号、最低账号数
  Expired-account cleanup, auto-registration, and minimum account count
- 临时邮箱提供商、DuckMail、MoEmail、FreeMail、GPTMail、CFMail 配置
  Temp-mail provider settings for DuckMail, MoEmail, FreeMail, GPTMail, and CFMail

请在云端管理后台修改这些业务配置；worker 每轮都会加载最新云端/存储配置。
Update business settings in the cloud admin panel; the worker loads the latest cloud/storage config on each cycle.

## 远程模式接口 / Remote Mode APIs

远程模式会调用：
Remote mode uses:

- `POST /login`
- `GET /admin/settings`
- `GET /admin/accounts-config`
- `PUT /admin/accounts-config`

其中 `/admin/settings` 返回的 `refresh_settings` 是刷新 worker 的业务配置来源。
The `refresh_settings` object from `/admin/settings` is the worker's business configuration source.

## 刷新流程 / Refresh Flow

1. 加载最新云端/存储配置。
   Load latest cloud/storage config.
2. 筛选即将过期的账号。
   Select accounts close to expiration.
3. 串行执行浏览器自动化刷新，避免同一账号重复并发。
   Run browser refresh tasks serially to avoid duplicate concurrent refreshes.
4. 写回新凭证和账号状态。
   Persist refreshed credentials and account status.
5. 按云端配置执行过期清理和自动注册。
   Run cleanup and auto-registration according to cloud settings.

## 故障排查 / Troubleshooting

### `DATABASE_URL or REMOTE_PROJECT_BASE_URL not configured`

- 至少配置一种存储后端。
  Configure at least one storage backend.
- 推荐运行 `python -m worker.cli wizard` 写入远程模式配置。
  Prefer `python -m worker.cli wizard` for remote mode setup.

### Google 无法访问 / Google Is Unreachable

- 先运行 `python -m worker.cli google`。
  Run `python -m worker.cli google` first.
- 如果这台 worker 需要代理访问 Google，请在云端管理后台配置 `proxy_for_auth`。
  If this worker needs a proxy to reach Google, configure `proxy_for_auth` in the cloud admin panel.

### `scheduled refresh disabled, sleeping`

- 云端配置里定时刷新关闭了。
  Scheduled refresh is disabled in cloud settings.
- 到云端管理后台开启定时刷新即可，本地业务覆盖变量已不再生效。
  Enable scheduled refresh in the cloud admin panel; local business override variables no longer apply.

### `no accounts need refresh`

- 账号还没进入刷新窗口，或云端刷新窗口配置太小。
  Accounts are not within the refresh window, or the cloud refresh window is too small.
- 到云端管理后台调大刷新窗口。
  Increase the refresh window in the cloud admin panel.

## 健康检查 / Health Check

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

## 和主服务的关系 / Relationship With Main Service

- 主服务负责管理后台、账号配置和 API 网关。
  The main service handles the admin panel, account config, and API gateway.
- `refresh-worker` 只负责账号刷新执行。
  `refresh-worker` only executes account refresh tasks.
- 远程模式下，本地 worker 仍然执行浏览器自动化，只是数据通过远端管理接口读写。
  In remote mode, browser automation still runs on the worker machine; only data I/O goes through remote admin APIs.
