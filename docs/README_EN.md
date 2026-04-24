<p align="center">
  <img src="../docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">Gemini Business → OpenAI-compatible API gateway</p>
<p align="center">
  <a href="../README.md">简体中文</a> | <strong>English</strong>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-CNC--1.0-red.svg" /> <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>
<p align="center"><strong>Current stable release: v0.3.2</strong> | <a href="https://github.com/yukkcat/gemini-business2api/releases/tag/v0.3.2">Release Notes</a> | <a href="https://github.com/yukkcat/gemini-business2api/releases">All Releases</a></p>

> [!IMPORTANT]
> Since **v0.3.0**, the repository mainline has been fully narrowed into a **2API-focused mainline**:
> only **the 2API main service**, **the admin panel**, and **the optional refresh-worker** remain.
>
> The legacy registration tool, registration flow, built-in refresh executor, and browser-display-dependent old paths have been removed or moved out. If you need refresh capability, attach the standalone `refresh-worker` branch / image on demand.

---

## Project Positioning

Gemini Business2API turns [Gemini Business](https://business.gemini.google) into an **OpenAI-compatible API gateway** with a built-in admin panel for managing account pools, system settings, image / video capability, runtime monitoring, and logs.

The current mainline has a very clear goal: provide a stable **2API main service** and keep historical registration, refresh, and experimental flows out of the primary repository path.

---

## Contact

Join the Business2API group:

- [https://qm.qq.com/q/yegwCqJisS](https://qm.qq.com/q/yegwCqJisS)

---

## Core Capabilities

- OpenAI-compatible endpoints for common OpenAI SDKs and middleware
- Multi-account scheduling with rotation, availability switching, and batch management
- Admin panel for import / export / edit / batch actions / status filtering
- Multimodal support across text, files, images, and video-related flows
- Image generation / image editing with Base64 or URL output
- Video generation with unified output control
- Centralized settings for proxy, mail, refresh, and output behavior
- Dashboard / monitoring / logs / gallery for runtime visibility
- SQLite / PostgreSQL support
- Optional `refresh-worker` integration without tight coupling to the main service

---

## Model Support Overview

| Model ID                 | Vision | Native Web | File Multimodal | Image Gen | Video Gen |
| ------------------------ | ------ | ---------- | --------------- | --------- | --------- |
| `gemini-auto`            | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-2.5-flash`       | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-2.5-pro`         | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-3-flash-preview` | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-3.1-pro-preview` | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-imagen`          | ✅      | ✅          | ✅               | ✅         | -         |
| `gemini-veo`             | ✅      | ✅          | ✅               | -         | ✅         |

> `gemini-imagen` is the dedicated image generation model, and `gemini-veo` is the dedicated video generation model.

---

## Functional Architecture

```mermaid
flowchart TB
  Admin["Admin user"] --> Frontend["Admin panel frontend"]
  Client["OpenAI-compatible client"] --> Gateway["2API gateway"]

  subgraph Features["Admin feature modules"]
    Dashboard["Overview"]
    Accounts["Account management"]
    Settings["System settings"]
    Monitor["Monitoring"]
    Logs["Runtime logs"]
    Gallery["Image gallery"]
    Docs["Docs / tutorials"]
  end

  Frontend --> Dashboard
  Frontend --> Accounts
  Frontend --> Settings
  Frontend --> Monitor
  Frontend --> Logs
  Frontend --> Gallery
  Frontend --> Docs

  Dashboard --> AdminAPI["Admin APIs"]
  Accounts --> AdminAPI
  Settings --> AdminAPI
  Monitor --> AdminAPI
  Logs --> AdminAPI
  Gallery --> AdminAPI
  Docs --> AdminAPI

  Gateway --> Runtime["Model / chat / image / video APIs"]
  AdminAPI --> Domain["Account pool / config / scheduling / monitoring / logs"]
  Runtime --> Domain

  Domain --> DB["SQLite / PostgreSQL"]
  Domain --> Data["data directory"]
  Domain -. "optional integration" .-> Refresh["refresh-worker"]
```

Current mainline: **the frontend focuses on 2API + admin management, while refresh is attached as an optional worker.**

---

## Deployment Layout

```text
docker-compose.yml
├─ gemini-api
│  ├─ runs the 2API main service
│  ├─ runs the admin panel
│  ├─ exposes 7860
│  └─ mounts ./data:/app/data
│
└─ refresh-worker (optional)
   ├─ disabled by default
   ├─ enabled with profile refresh
   ├─ does not expose business APIs
   ├─ reads the same ./data volume
   └─ handles account refresh work
```

- Mainline 2API only: `docker compose up -d`
- Attach refresh worker when needed: `docker compose --profile refresh up -d`

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/yukkcat/gemini-business2api.git
cd gemini-business2api
cp .env.example .env
# Set at least ADMIN_KEY

docker compose up -d
```

Enable `refresh-worker` if needed:

```bash
docker compose --profile refresh up -d
```

### Option 2: Interactive installer script

The interactive installer is intended for guided command-line setup. During execution it prompts for the following configuration items:

- whether to use **Docker deployment** or **local Python mode**
- which service port to use
- the `ADMIN_KEY`
- the `DATABASE_URL`
- **whether to enable refresh-worker**

Default install:

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/deploy/install.sh | sudo bash
```

Pin to the current stable release:

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/v0.3.2/deploy/install.sh | sudo bash
```

Preset `refresh-worker` to enabled by default:

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/deploy/install.sh | sudo bash -s -- --with-refresh
```

> `--with-refresh` only presets the default answer for enabling refresh-worker.
> It does not represent a separate installation flow.

---


## Access URLs

- Admin panel: `http://localhost:7860/`
- OpenAI-compatible endpoint: `http://localhost:7860/v1/chat/completions`
- Health check: `http://localhost:7860/health`

---

## Configuration & Data Boundaries

### Key `.env` entries

```env
ADMIN_KEY=your-admin-login-key
# PORT=7860
# DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
# REFRESH_WORKER_IMAGE=cooooookk/gemini-refresh-worker:latest
# REFRESH_HEALTH_PORT=8080
```

Notes:

- the main service image comes from the mainline repository
- `REFRESH_WORKER_IMAGE` points to the image built from the standalone refresh-worker branch
- local SQLite is used by default when `DATABASE_URL` is not set
- PostgreSQL can be enabled by setting `DATABASE_URL`

### Data directory

Compose mounts:

```text
./data -> /app/data
```

This directory stores:

- the SQLite database
- runtime persistence data
- locally generated files and caches

---

## API Compatibility Endpoints

| Endpoint                 | Method | Description      |
| ------------------------ | ------ | ---------------- |
| `/v1/models`             | GET    | model list       |
| `/v1/chat/completions`   | POST   | chat completions |
| `/v1/images/generations` | POST   | image generation |
| `/v1/images/edits`       | POST   | image editing    |
| `/health`                | GET    | health check     |

---

## Optional: Tampermonkey Import Helper

If you want one-click export of importable account JSON from Gemini Business pages, install the Tampermonkey userscript:

- Install URL: [gemini-business-import.user.js](https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/tools/tampermonkey/gemini-business-import.user.js)
- Repository path: `tools/tampermonkey/gemini-business-import.user.js`
- Click `Copy JSON` to copy; `Shift + Click` to download a JSON file
- Exported `expires_at` defaults to **current time + 12 hours**

Before use, make sure:

1. Tampermonkey -> **General** -> **Config mode**: `Advanced`
2. Tampermonkey -> **Security** -> **Allow scripts to access cookies**: `All`
3. If cookie access is still blocked, enable **Developer mode** on the browser extensions page
4. Refresh `business.gemini.google` and try again

The script will show a popup reminder when cookie access is unavailable.

---
## License

This project uses the **Cooperative Non-Commercial License (CNC-1.0)**.

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yukkcat/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#yukkcat/gemini-business2api&type=date&legend=top-left)

**If this project helps you, please give it a ⭐ Star!**

