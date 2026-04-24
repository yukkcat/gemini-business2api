<p align="center">
  <img src="docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">Gemini Business → OpenAI 兼容 API 网关</p>
<p align="center">
  <strong>简体中文</strong> | <a href="docs/README_EN.md">English</a>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-CNC--1.0-red.svg" /> <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>
<p align="center"><strong>当前稳定版本：v0.3.2</strong> | <a href="https://github.com/yukkcat/gemini-business2api/releases/tag/v0.3.2">发布说明</a> | <a href="https://github.com/yukkcat/gemini-business2api/releases">全部版本</a></p>

> [!IMPORTANT]
> 自 **v0.3.0** 起，主线仓库已彻底归为 **2API 主线**：
> 只保留 **2API 主服务**、**管理后台**、**可选 refresh-worker**。
>
> 已移除或迁出：**注册机**、**注册流程**、**主服务内嵌刷新执行器**、**依赖浏览器显示环境的旧链路**。如需刷新能力，请通过独立的 `refresh-worker` 分支 / 镜像按需接入。

---

## 项目定位

Gemini Business2API 是一个把 [Gemini Business](https://business.gemini.google) 能力转换为 **OpenAI 兼容接口** 的网关服务，内置后台管理面板，适合统一管理账号池、系统设置、图片 / 视频能力与运行状态。

当前主线目标很明确：**稳定提供 2API 主服务**，把历史上的注册、刷新、实验性链路从主仓库主流程中彻底拆出去。

---

## 联系我们

点击链接加入群聊【Business2API 交流群】：

- [https://qm.qq.com/q/yegwCqJisS](https://qm.qq.com/q/yegwCqJisS)

---

## 核心能力

- OpenAI 兼容接口，可直接对接常见 OpenAI SDK / 中间层
- 多账号调度，支持轮询、可用性切换、批量管理
- 管理后台，支持账号导入 / 导出 / 编辑 / 批量操作 / 状态筛选
- 多模态能力，覆盖文本、文件、图片、视频相关链路
- 图片生成 / 图片编辑，支持 Base64 或 URL 输出
- 视频生成与统一输出控制
- 系统设置统一收口，集中管理代理、邮箱、刷新、输出格式等配置
- 仪表盘 / 监控 / 日志 / 画廊，方便观察服务状态
- 支持 SQLite / PostgreSQL
- 可选接入 `refresh-worker`，但不再与主服务强耦合

---

## 模型能力概览

| 模型 ID                  | 识图 | 原生联网 | 文件多模态 | 图片生成 | 视频生成 |
| ------------------------ | ---- | -------- | ---------- | -------- | -------- |
| `gemini-auto`            | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-2.5-flash`       | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-2.5-pro`         | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-3-flash-preview` | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-3.1-pro-preview` | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-imagen`          | ✅    | ✅        | ✅          | ✅        | -        |
| `gemini-veo`             | ✅    | ✅        | ✅          | -        | ✅        |

> `gemini-imagen` 为专用图片生成模型，`gemini-veo` 为专用视频生成模型。

---

## 功能架构

```mermaid
flowchart TB
  Admin["管理员"] --> Frontend["管理后台前端"]
  Client["OpenAI 兼容客户端"] --> Gateway["2API 网关"]

  subgraph Features["后台功能模块"]
    Dashboard["概览中心"]
    Accounts["账号管理"]
    Settings["系统设置"]
    Monitor["监控状态"]
    Logs["运行日志"]
    Gallery["图片画廊"]
    Docs["文档教程"]
  end

  Frontend --> Dashboard
  Frontend --> Accounts
  Frontend --> Settings
  Frontend --> Monitor
  Frontend --> Logs
  Frontend --> Gallery
  Frontend --> Docs

  Dashboard --> AdminAPI["后台管理接口"]
  Accounts --> AdminAPI
  Settings --> AdminAPI
  Monitor --> AdminAPI
  Logs --> AdminAPI
  Gallery --> AdminAPI
  Docs --> AdminAPI

  Gateway --> Runtime["模型 / 对话 / 图片 / 视频接口"]
  AdminAPI --> Domain["账号池 / 配置中心 / 调度 / 监控 / 日志"]
  Runtime --> Domain

  Domain --> DB["SQLite / PostgreSQL"]
  Domain --> Data["data 目录"]
  Domain -. "可选接入" .-> Refresh["refresh-worker"]
```

当前主线：**前台只做 2API 与后台管理，刷新能力按可选 worker 外挂接入。**

---

## 部署结构

```text
docker-compose.yml
├─ gemini-api
│  ├─ 运行 2API 主服务
│  ├─ 运行管理后台
│  ├─ 暴露 7860
│  └─ 挂载 ./data:/app/data
│
└─ refresh-worker（可选）
   ├─ 默认不启动
   ├─ 使用 profile refresh 启动
   ├─ 不暴露业务 API
   ├─ 读取同一个 ./data
   └─ 负责账号刷新
```

- 主线只跑 2API：`docker compose up -d`
- 如需接入刷新 worker：`docker compose --profile refresh up -d`

---

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/yukkcat/gemini-business2api.git
cd gemini-business2api
cp .env.example .env
# 至少设置 ADMIN_KEY

docker compose up -d
```

如需启用 refresh-worker：

```bash
docker compose --profile refresh up -d
```

### 方式二：交互式安装脚本

交互式安装脚本适用于需要命令行引导安装的场景。执行过程中会提示填写或选择以下配置项：

- 使用 **Docker 部署** 还是 **Python 本地模式**
- 服务端口
- `ADMIN_KEY`
- `DATABASE_URL`
- **是否启用 refresh-worker**

默认安装：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/deploy/install.sh | sudo bash
```

固定到当前正式版：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/v0.3.2/deploy/install.sh | sudo bash
```

预设 `refresh-worker` 默认开启：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/deploy/install.sh | sudo bash -s -- --with-refresh
```

> `--with-refresh` 用于将“是否启用 refresh-worker”的默认选项预设为开启，
> 并不代表另一套独立安装流程。

---

## 访问地址

- 管理后台：`http://localhost:7860/`
- OpenAI 兼容接口：`http://localhost:7860/v1/chat/completions`
- 健康检查：`http://localhost:7860/health`

---

## 配置与数据边界

### `.env` 关键项

```env
ADMIN_KEY=your-admin-login-key
# PORT=7860
# DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
# REFRESH_WORKER_IMAGE=cooooookk/gemini-refresh-worker:latest
# REFRESH_HEALTH_PORT=8080
```

说明：

- 主服务镜像来自当前主线仓库
- `REFRESH_WORKER_IMAGE` 指向独立 refresh-worker 分支产出的镜像
- 未配置 `DATABASE_URL` 时默认使用本地 SQLite（推荐）
- 配置 `DATABASE_URL` 后可切换到 PostgreSQL

### 数据目录

Compose 默认挂载：

```text
./data -> /app/data
```

这里会保存：

- SQLite 数据库
- 运行时持久化数据
- 本地生成文件与缓存

---

## API 兼容接口

| 接口                     | 方法 | 说明     |
| ------------------------ | ---- | -------- |
| `/v1/models`             | GET  | 模型列表 |
| `/v1/chat/completions`   | POST | 对话补全 |
| `/v1/images/generations` | POST | 图片生成 |
| `/v1/images/edits`       | POST | 图片编辑 |
| `/health`                | GET  | 健康检查 |

---

## 可选：油猴导入助手

如需从 Gemini Business 页面一键复制可导入账号 JSON，可安装 Tampermonkey 用户脚本：

- 安装地址：[gemini-business-import.user.js](https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/tools/tampermonkey/gemini-business-import.user.js)
- 仓库位置：`tools/tampermonkey/gemini-business-import.user.js`
- 点击 `Copy JSON` 复制；`Shift + Click` 下载 JSON 文件
- 导出的 `expires_at` 默认是**当前时间 + 12 小时**

使用前请先确认：

1. Tampermonkey -> **通用** -> **配置模式**：`高级`
2. Tampermonkey -> **安全** -> **允许脚本访问 Cookie**：`All`
3. 如果仍然没有 Cookie 权限，请在浏览器扩展页开启**开发者模式**
4. 修改后刷新 `business.gemini.google` 页面再试

脚本如果检测不到 Cookie 权限，会直接弹窗提醒上述设置。

---
## 许可证

本项目采用 **Cooperative Non-Commercial License (CNC-1.0)**。

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yukkcat/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#yukkcat/gemini-business2api&type=date&legend=top-left)

**如果这个项目对你有帮助，请给个 ⭐ Star！**

