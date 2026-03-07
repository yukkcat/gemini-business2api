# gemini-refresh-worker

独立部署的 Gemini Business 账户自动刷新服务，从 [gemini-business2api](https://github.com/Dreamy-rain/gemini-business2api) 主项目中拆分而来。

连接与主服务相同的数据库，自动检测即将过期的账户并通过浏览器自动化重新登录获取新凭证。

## 功能

- 定时轮询数据库，检测 cookie 即将过期的账户
- 使用 Chromium 浏览器自动化完成 Gemini Business 登录
- 支持多种邮箱验证码提供商（DuckMail、Moemail、Freemail、GPTMail、Microsoft OAuth）
- **自动删除过期账户**：试用期（`trial_end`）到期后自动清理数据库中的账户记录
- **自动注册补充账户**：活跃账户数低于阈值时自动注册新账户
- 环境变量独立控制，可覆盖数据库中的配置
- 支持 PostgreSQL 和 SQLite 两种数据库后端
- 内置 HTTP 健康检查端口
- Docker 一键部署

## 项目结构

```
.
├── .github/workflows/
│   └── docker-build.yml       # GitHub Actions 自动构建镜像
├── worker/
│   ├── main.py                # 入口：轮询循环 + 健康检查
│   ├── config.py              # 配置管理（数据库 + 环境变量覆盖）
│   ├── storage.py             # 数据库抽象（PostgreSQL / SQLite）
│   ├── refresh_service.py     # 刷新编排：过期检测 + 过期删除 + 自动注册 + 任务执行
│   ├── register_service.py    # 账号注册服务（自动注册新账号）
│   ├── gemini_automation.py   # 浏览器自动化（DrissionPage/Chromium，支持刷新和注册）
│   ├── mail_utils.py          # 验证码提取
│   ├── proxy_utils.py         # 代理解析
│   ├── child_reaper.py        # 僵尸进程清理
│   └── mail_clients/          # 邮箱客户端
│       ├── __init__.py        # 工厂函数
│       ├── duckmail_client.py
│       ├── freemail_client.py
│       ├── gptmail_client.py
│       ├── moemail_client.py
│       └── microsoft_mail_client.py
├── Dockerfile
├── docker-compose.yml           # 从源码构建部署
├── docker-compose.deploy.yml    # 拉取镜像直接部署
├── entrypoint.sh
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 快速开始

### 前置条件

- 已部署 gemini-business2api 主服务并有可用的数据库
- 数据库中已配置账户（通过主服务管理面板添加）

### 方式一：使用预构建镜像部署（推荐）

无需克隆代码，直接拉取镜像运行。

1. 创建 `.env` 文件：

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
FORCE_REFRESH_ENABLED=true
REFRESH_INTERVAL_MINUTES=30
BROWSER_HEADLESS=true
HEALTH_PORT=8080
LOG_LEVEL=INFO
```

2. 使用 `docker run` 直接运行：

```bash
docker run -d \
  --name gemini-refresh-worker \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  your_dockerhub_username/gemini-refresh-worker:latest
```

或者下载 [`docker-compose.deploy.yml`](docker-compose.deploy.yml) 后放在与 `.env` 同一目录：

```bash
export DOCKERHUB_USERNAME=your_dockerhub_username
docker-compose -f docker-compose.deploy.yml up -d
```

### 方式二：从源码构建部署

```bash
git clone https://github.com/YOUR_USERNAME/gemini-refresh-worker.git
cd gemini-refresh-worker
cp .env.example .env
# 编辑 .env，至少配置 DATABASE_URL
docker-compose up -d --build
```

查看日志：

```bash
docker-compose logs -f
```

### 方式三：手动构建并推送镜像

适合需要自建镜像仓库或自定义镜像的场景。

```bash
# 构建多架构镜像并推送到 Docker Hub
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t your_dockerhub_username/gemini-refresh-worker:latest \
  --push .
```

推送后，在任意机器上只需 `docker pull` 即可使用。

### 本地运行（无 Docker）

```bash
pip install -r requirements.txt
# 安装 Chromium 浏览器
# 配置 .env 文件
python -m worker.main
```

## 配置

Worker 的配置来自两个来源，环境变量优先级高于数据库：

### 数据库配置（从主服务管理面板设置）

Worker 每个轮询周期都会从数据库重新读取配置（热更新），包括：
- 定时刷新开关和间隔
- 邮箱提供商设置
- 代理设置
- 浏览器无头模式

### 环境变量（覆盖数据库配置）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接字符串（必填） | — |
| `LOG_LEVEL` | 日志级别：DEBUG, INFO, WARNING, ERROR | `INFO` |
| `HEALTH_PORT` | 健康检查端口，0 = 禁用 | `0` |
| `FORCE_REFRESH_ENABLED` | 强制开启/关闭定时刷新（覆盖数据库设置） | 未设置（使用数据库值） |
| `REFRESH_INTERVAL_MINUTES` | 刷新检测间隔，分钟（1-720） | 未设置（使用数据库值） |
| `REFRESH_WINDOW_HOURS` | 过期窗口，小时（0-24），在此窗口内的账户将被刷新 | 未设置（使用数据库值） |
| `BROWSER_HEADLESS` | 浏览器无头模式 | 未设置（使用数据库值） |
| `PROXY_FOR_AUTH` | 认证代理地址 | 未设置（使用数据库值） |
| `DELETE_EXPIRED_ACCOUNTS` | 自动删除试用期（`trial_end`）已到期的账户 | 未设置（使用数据库值） |
| `AUTO_REGISTER_ENABLED` | 账户不足时自动注册新账户 | 未设置（使用数据库值） |
| `MIN_ACCOUNT_COUNT` | 最低活跃账户数量，低于此值触发自动注册（0 = 禁用） | 未设置（使用数据库值） |
| `REGISTER_DOMAIN` | 注册账号使用的邮箱域名（DuckMail 专用） | 未设置（使用数据库值） |
| `REGISTER_DEFAULT_COUNT` | 单次注册账号数量（1-20） | 未设置（使用数据库值） |

**典型独立部署配置**：

```env
DATABASE_URL=postgresql://user:password@db-host:5432/gemini
FORCE_REFRESH_ENABLED=true
REFRESH_INTERVAL_MINUTES=30
BROWSER_HEADLESS=true
HEALTH_PORT=8080
DELETE_EXPIRED_ACCOUNTS=true
AUTO_REGISTER_ENABLED=true
MIN_ACCOUNT_COUNT=5
```

这样 Worker 不依赖主服务面板来控制刷新开关，完全通过环境变量独立运行。

## 工作原理

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  轮询循环     │────▶│  过期检测      │────▶│  浏览器自动化  │
│  (interval)  │     │  (window_hrs) │     │  (Chromium)   │
└─────────────┘     └──────────────┘     └──────────────┘
       │                    │                     │
       ▼                    ▼                     ▼
  重新加载配置          读取账户列表           登录 + 获取凭证
  (热更新)            检查 expires_at          更新数据库
       │
       ▼
  ┌──────────────┐     ┌──────────────┐
  │  过期清理      │────▶│  自动注册      │
  │  (可选)       │     │  (可选)       │
  └──────────────┘     └──────────────┘
       │                     │
       ▼                     ▼
  删除试用期到期账户     注册新账户补充
```

1. **轮询循环**：按配置的间隔（默认 30 分钟）周期性检查
2. **过期检测**：从数据库加载所有账户，找出 `expires_at` 在刷新窗口内的账户
3. **浏览器自动化**：启动 Chromium，模拟登录 Gemini Business，提取新的 cookie
4. **邮箱验证码**：如果登录需要验证码，自动通过配置的邮箱提供商获取
5. **保存结果**：将新的凭证和过期时间写回数据库
6. **过期清理**（可选）：删除试用期（`trial_end`）已到期的账户记录
7. **自动注册**（可选）：当活跃账户数低于 `MIN_ACCOUNT_COUNT` 时，自动注册新账户补充

## 健康检查

当 `HEALTH_PORT` > 0 时，Worker 会在指定端口启动一个 HTTP 健康检查服务：

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

Docker 的 `HEALTHCHECK` 已配置为自动检查此端口。

## 与主服务的关系

- Worker 和主服务共享同一个数据库
- Worker 只**读取**账户列表和配置，**更新**账户凭证和任务历史
- 不会修改主服务的 API 网关功能
- 可以和主服务部署在不同的机器上，只要能访问同一个数据库

## 故障排查

**Worker 启动失败 "DATABASE_URL not configured"**
- 确保 `.env` 文件中配置了 `DATABASE_URL`，或通过环境变量传入

**日志显示 "scheduled refresh disabled, sleeping"**
- 数据库中的定时刷新未开启，且未设置 `FORCE_REFRESH_ENABLED=true`
- 设置 `FORCE_REFRESH_ENABLED=true` 即可独立控制

**日志显示 "no accounts need refresh"**
- 所有账户的 cookie 尚未接近过期，无需刷新
- 可调大 `REFRESH_WINDOW_HOURS` 来提前刷新

**浏览器自动化失败**
- 确保 Chromium 已安装（Docker 镜像已内置）
- 确保 Xvfb 正在运行（Docker entrypoint 已自动启动）
- 检查代理设置是否正确

## CI/CD 自动构建

项目已配置 GitHub Actions（`.github/workflows/docker-build.yml`），推送到 `main` 分支时会自动构建 `linux/amd64` + `linux/arm64` 多架构镜像并推送到 Docker Hub。

需要在 GitHub 仓库的 Settings → Secrets and variables → Actions 中配置：
- `DOCKERHUB_USERNAME` — Docker Hub 用户名
- `DOCKERHUB_TOKEN` — Docker Hub Access Token

也可以手动触发（workflow_dispatch），或通过打 `v*` 格式的 tag 触发。

## 常见部署平台

### Render / Railway / Fly.io

这类平台支持直接填入 Docker 镜像地址部署：

1. 指定镜像：`your_dockerhub_username/gemini-refresh-worker:latest`
2. 配置环境变量（`DATABASE_URL`, `FORCE_REFRESH_ENABLED=true` 等）
3. 健康检查路径设为 `/health`，端口 `8080`

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gemini-refresh-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gemini-refresh-worker
  template:
    metadata:
      labels:
        app: gemini-refresh-worker
    spec:
      containers:
        - name: worker
          image: your_dockerhub_username/gemini-refresh-worker:latest
          envFrom:
            - secretRef:
                name: gemini-worker-secrets
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
```

## Remote Beta Mode (local worker + remote beta)

`refresh-worker` now supports a remote project mode.  
In this mode, local worker executes browser automation locally, but account/settings data is read/written through remote beta admin APIs.

Required environment variables:

```env
REMOTE_PROJECT_BASE_URL=https://your-beta-domain.example
REMOTE_PROJECT_PASSWORD=your_admin_key
```

Optional:

```env
REMOTE_PROJECT_VERIFY_SSL=true
REMOTE_PROJECT_TIMEOUT_SECONDS=30
```

When `REMOTE_PROJECT_BASE_URL` is set, storage backend switches to `remote` automatically.

Remote API endpoints used:

- `POST /login`
- `GET /admin/settings`
- `GET /admin/accounts-config`
- `PUT /admin/accounts-config`

This is the recommended setup for:

- Remote deployment: `beta` (public/admin service)
- Local machine: `refresh-worker` (browser execution node)

## CLI (Chinese interactive mode)

For local operation, you can use the CLI instead of only daemon mode:

```bash
python -m worker.cli
```

Useful subcommands:

- `python -m worker.cli once` : run one refresh round immediately
- `python -m worker.cli doctor` : print config + test remote connectivity
- `python -m worker.cli wizard` : write remote-mode values into `.env`
- `python -m worker.cli poll` : start polling in foreground

Docker keeps using daemon mode (`python -m worker.main`) by default.
If you need manual trigger inside container:

```bash
docker compose exec refresh-worker python -m worker.cli once
```
