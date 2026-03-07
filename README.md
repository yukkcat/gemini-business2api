# gemini-refresh-worker

独立部署的 Gemini Business 账户刷新服务。  
Standalone refresh service for Gemini Business accounts.

它从主项目 [gemini-business2api](https://github.com/Dreamy-rain/gemini-business2api) 中拆分而来，专注于“检测即将过期账号并自动刷新凭证”。  
It is split from the main project and focuses on detecting expiring accounts and refreshing credentials automatically.

## 推荐场景 / Recommended Topology

- 远程部署一套 `beta`（提供管理面板与 API）。  
  Deploy one remote `beta` instance (admin panel + API).
- 本地运行 `refresh-worker`（执行浏览器自动化刷新）。  
  Run `refresh-worker` locally (browser automation executor).
- 不需要本地再部署第二套 `beta`。  
  You do not need a second local `beta`.

## 功能概览 / Feature Overview

- 定时轮询刷新即将过期账号。  
  Scheduled polling for accounts close to expiration.
- 支持手动触发“一次刷新”。  
  Supports manual "run once" refresh.
- 支持远程项目模式（通过远程管理 API 拉取/回写数据）。  
  Supports remote project mode (read/write via remote admin APIs).
- 支持本机代理诊断（Google 连通性检测）。  
  Built-in local proxy/Google connectivity diagnostics.
- 支持自动删除过期账号、自动补充注册账号（可选）。  
  Optional lifecycle automation: delete expired accounts and auto-register new ones.

## 快速开始 / Quick Start

### 1) 准备环境变量 / Prepare environment variables

```bash
cp .env.example .env
```

按你的场景填写 `.env`。  
Fill `.env` based on your deployment mode.

### 2) 选择存储模式（二选一）/ Choose storage mode (pick one)

**模式 A：数据库直连 / Mode A: direct database**

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

**模式 B：远程项目模式（推荐）/ Mode B: remote project (recommended)**

```env
REMOTE_PROJECT_BASE_URL=https://your-beta-domain.example
REMOTE_PROJECT_PASSWORD=your_admin_key
```

如果两个都配置了，优先使用远程项目模式。  
If both are configured, remote project mode takes precedence.

可选：设置浏览器模式（默认 `normal`）。  
Optional: set browser mode (default `normal`).

```env
BROWSER_MODE=silent
```

### 3) 启动方式 / Run options

**本地 Python 运行 / Run with Python**

```bash
pip install -r requirements.txt
python -m worker.main
```

**本地交互菜单 / Interactive console**

```bash
python -m worker.cli
```

**Docker Compose（源码）/ Docker Compose (from source)**

```bash
docker compose up -d --build
```

**Docker（镜像）/ Docker (image)**

```bash
docker run -d \
  --name gemini-refresh-worker \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  your_dockerhub_username/gemini-refresh-worker:latest
```

### 4) 手动执行一次刷新 / Trigger one refresh manually

```bash
python -m worker.cli once
```

### 5) 健康检查 / Health check

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

## CLI 命令 / CLI Commands

| 命令 / Command | 说明（中文） | Description (English) |
|---|---|---|
| `python -m worker.cli` | 打开交互菜单 | Open interactive menu |
| `python -m worker.cli once` | 立即执行一轮刷新 | Run one refresh immediately |
| `python -m worker.cli poll` | 前台守护轮询 | Start foreground polling loop |
| `python -m worker.cli doctor` | 配置 + 远程连接 + Google 诊断 | Config + remote check + Google diagnostics |
| `python -m worker.cli google` | 仅做 Google/代理诊断 | Google/proxy diagnostics only |
| `python -m worker.cli wizard` | 交互写入 `.env` | Interactive `.env` setup wizard |
| `python -m worker.cli lang en --save` | 切换语言并写入 `.env` | Switch language and persist into `.env` |

交互菜单里也提供语言切换选项，默认中文。  
Language switch is also available in interactive menu, default is Chinese.

## 环境变量 / Environment Variables

### 核心变量 / Core variables

| 变量 | 中文说明 | English |
|---|---|---|
| `DATABASE_URL` | 直连数据库模式连接串 | DB URL for direct database mode |
| `REMOTE_PROJECT_BASE_URL` | 远程项目地址（beta 地址） | Remote project base URL (beta URL) |
| `REMOTE_PROJECT_PASSWORD` | 远程管理密码（登录密码 / ADMIN_KEY） | Remote admin password (login password / ADMIN_KEY) |
| `CLI_LANG` | CLI 语言（`zh`/`en`，默认 `zh`） | CLI language (`zh`/`en`, default `zh`) |
| `LOG_LEVEL` | 日志级别：`DEBUG/INFO/WARNING/ERROR` | Log level |
| `HEALTH_PORT` | 健康检查端口，`0` 为关闭 | Health check port (`0` disables) |

### 远程模式变量 / Remote mode variables

| 变量 | 中文说明 | English |
|---|---|---|
| `REMOTE_PROJECT_VERIFY_SSL` | 是否校验远程 HTTPS 证书 | Verify remote HTTPS certificate |
| `REMOTE_PROJECT_TIMEOUT_SECONDS` | 远程 API 超时时间（秒） | Remote API timeout in seconds |
| `REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH` | 是否继承远程 `proxy_for_auth`（默认 `false`） | Whether to inherit remote `proxy_for_auth` (default `false`) |

### 刷新覆盖变量 / Refresh override variables

| 变量 | 中文说明 | English |
|---|---|---|
| `FORCE_REFRESH_ENABLED` | 强制开关定时刷新（覆盖存储配置） | Force scheduled refresh on/off (override storage config) |
| `REFRESH_INTERVAL_MINUTES` | 刷新检测间隔（分钟） | Refresh check interval in minutes |
| `REFRESH_WINDOW_HOURS` | 过期窗口（小时） | Expiration window in hours |
| `BROWSER_MODE` | 浏览器模式：`normal`/`silent`/`headless` | Browser mode: `normal`/`silent`/`headless` |
| `BROWSER_HEADLESS` | 兼容旧字段（若设置了 `BROWSER_MODE` 将被忽略） | Legacy compatibility field (ignored when `BROWSER_MODE` is set) |
| `PROXY_FOR_AUTH` | 本机认证代理（如 `socks5h://127.0.0.1:7890`） | Local auth proxy |

浏览器模式建议：  
Browser mode recommendations:

- `normal`：正常有头窗口，适合人工观察。  
  `normal`: regular headed window, good for active observation.
- `silent`：有头运行但尽量最小化，减少抢占焦点。  
  `silent`: headed but minimized to reduce focus stealing.
- `headless`：完全无头，资源占用更低。  
  `headless`: fully headless, usually lower resource usage.

### 账号生命周期变量 / Account lifecycle variables

| 变量 | 中文说明 | English |
|---|---|---|
| `DELETE_EXPIRED_ACCOUNTS` | 自动删除凭证过期账号 | Auto-delete accounts with expired credentials |
| `AUTO_REGISTER_ENABLED` | 自动补充注册账号 | Auto-register new accounts when needed |
| `MIN_ACCOUNT_COUNT` | 最低活跃账号数量阈值 | Minimum active account threshold |
| `REGISTER_DOMAIN` | 注册邮箱域名（DuckMail） | Registration email domain (DuckMail) |
| `REGISTER_DEFAULT_COUNT` | 单批注册数量（1-20） | Accounts to register per batch (1-20) |

## 远程模式说明 / Remote Mode Notes

远程模式会通过以下接口读写数据：  
Remote mode reads/writes data via these endpoints:

- `POST /login`
- `GET /admin/settings`
- `GET /admin/accounts-config`
- `PUT /admin/accounts-config`

代理行为说明：  
Proxy behavior:

- 默认不继承远程站点 `proxy_for_auth`，避免把远程 `localhost` 代理误用到本机。  
  By default, remote `proxy_for_auth` is not inherited to avoid misusing remote `localhost` proxy locally.
- 如确有需要，可设置 `REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH=true`。  
  Set `REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH=true` only if needed.

## 刷新流程 / Refresh Flow

1. 读取最新配置（环境变量优先，支持热更新）。  
   Load latest config (env vars override storage; hot reload supported).
2. 根据刷新窗口筛选即将过期账号。  
   Select accounts that are close to expiration.
3. 串行执行刷新任务，避免重复并发刷新同一账号。  
   Execute refresh tasks serially to avoid duplicate concurrent refreshes.
4. 写回新凭证与状态。  
   Persist refreshed credentials and status.
5. 根据配置执行过期清理与自动注册。  
   Run optional expiry cleanup and auto-registration.

## 故障排查 / Troubleshooting

**1) 启动报错：`DATABASE_URL or REMOTE_PROJECT_BASE_URL not configured`**

- 需要至少配置一组存储后端。  
  You must configure at least one storage backend.

**2) 经常出现 Google 无法访问 / Google frequently unreachable**

- 先执行：`python -m worker.cli google`。  
  First run diagnostics with `python -m worker.cli google`.
- 确认本机代理可用并设置 `PROXY_FOR_AUTH`。  
  Confirm local proxy works and set `PROXY_FOR_AUTH`.
- 远程模式下默认不会继承远程代理，这属于设计行为。  
  In remote mode, not inheriting remote proxy is expected behavior.

**3) 日志显示 `scheduled refresh disabled, sleeping`**

- 存储配置里定时刷新关闭了。  
  Scheduled refresh is disabled in storage config.
- 可设置 `FORCE_REFRESH_ENABLED=true` 强制开启。  
  Set `FORCE_REFRESH_ENABLED=true` to force enable.

**4) 日志显示 `no accounts need refresh`**

- 账号未到刷新窗口。  
  Accounts are not within refresh window yet.
- 可调大 `REFRESH_WINDOW_HOURS`。  
  Increase `REFRESH_WINDOW_HOURS` if needed.

## 与主服务关系 / Relationship with Main Service

- Worker 与主服务可分机部署。  
  Worker and main service can run on different machines.
- Worker 负责账号刷新执行，不负责 API 网关业务。  
  Worker handles refresh execution, not API gateway logic.
- 远程模式下，本地 worker 仍执行浏览器自动化，只是数据从远程管理接口读写。  
  In remote mode, browser automation still runs locally; only data I/O goes through remote admin APIs.
