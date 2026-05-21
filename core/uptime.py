"""
Uptime 实时监控与心跳历史持久化。
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import json
import os
from threading import Lock

from core.model_aliases import normalize_model_name

# 北京时区 UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))

# 每个服务保留最近 60 条心跳
MAX_HEARTBEATS = 60
SLOW_THRESHOLD_MS = 40000
WARNING_STATUS_CODES = {429}

_storage_path: Optional[str] = None
_storage_lock = Lock()

# 服务注册表
SERVICES = {
    "api_service": {"name": "API 服务", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "account_pool": {"name": "服务资源", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-2.5-pro": {"name": "Gemini 2.5 Pro", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-3.1-flash": {"name": "Gemini 3.1 Flash", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-3.1-pro-preview": {"name": "Gemini 3.1 Pro Preview", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-imagen": {"name": "Gemini Imagen", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-veo": {"name": "Gemini Veo", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
}

SUPPORTED_MODELS = [
    "gemini-2.5-pro",
    "gemini-3.1-flash",
    "gemini-3.1-pro-preview",
    "gemini-imagen",
    "gemini-veo",
]


def configure_storage(path: Optional[str]) -> None:
    """配置心跳持久化路径。"""
    global _storage_path
    _storage_path = path


def _classify_level(success: bool, status_code: Optional[int], latency_ms: Optional[int]) -> str:
    if status_code in WARNING_STATUS_CODES:
        return "warn"
    if success and latency_ms is not None and latency_ms >= SLOW_THRESHOLD_MS:
        return "warn"
    return "up" if success else "down"


def _save_heartbeats() -> None:
    if not _storage_path:
        return
    try:
        payload = {}
        for service_id, service_data in SERVICES.items():
            payload[service_id] = list(service_data["heartbeats"])
        os.makedirs(os.path.dirname(_storage_path), exist_ok=True)
        with _storage_lock, open(_storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
    except Exception:
        return


def load_heartbeats() -> None:
    if not _storage_path or not os.path.exists(_storage_path):
        return
    try:
        with _storage_lock, open(_storage_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for service_id, heartbeats in payload.items():
            if service_id not in SERVICES:
                continue
            SERVICES[service_id]["heartbeats"].clear()
            for beat in heartbeats[-MAX_HEARTBEATS:]:
                SERVICES[service_id]["heartbeats"].append(beat)
    except Exception:
        return


def record_request(
    service: str,
    success: bool,
    latency_ms: Optional[int] = None,
    status_code: Optional[int] = None
):
    """记录一次心跳。"""
    service = normalize_model_name(service)
    if service not in SERVICES:
        return

    level = _classify_level(success, status_code, latency_ms)
    heartbeat = {
        "time": datetime.now(BEIJING_TZ).strftime("%H:%M:%S"),
        "success": success,
        "level": level,
    }
    if latency_ms is not None:
        heartbeat["latency_ms"] = latency_ms
    if status_code is not None:
        heartbeat["status_code"] = status_code

    SERVICES[service]["heartbeats"].append(heartbeat)
    _save_heartbeats()


def get_realtime_status() -> Dict:
    """返回实时监控数据。"""
    result = {"services": {}}

    for service_id, service_data in SERVICES.items():
        heartbeats = list(service_data["heartbeats"])
        total = len(heartbeats)
        success = sum(1 for h in heartbeats if h.get("success"))

        uptime = (success / total * 100) if total > 0 else 100.0

        last_status = "unknown"
        if heartbeats:
            last_level = heartbeats[-1].get("level")
            if last_level in {"up", "down", "warn"}:
                last_status = last_level
            else:
                last_status = "up" if heartbeats[-1].get("success") else "down"

        result["services"][service_id] = {
            "name": service_data["name"],
            "status": last_status,
            "uptime": round(uptime, 1),
            "total": total,
            "success": success,
            "heartbeats": heartbeats[-MAX_HEARTBEATS:],
        }

    result["updated_at"] = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return result


async def get_uptime_summary(days: int = 90) -> Dict:
    """兼容旧接口。"""
    return get_realtime_status()
