import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException, Request

from app.api.schemas import AdminSettingsPayload
from app.services.settings_service import get_settings_payload, update_settings


@dataclass(frozen=True)
class SettingsRouteDeps:
    apply_runtime_state: Callable[[dict[str, Any]], None]
    build_retry_policy: Callable[[], Any]
    config_manager: Any
    create_http_client: Callable[[str | None], Any]
    get_config: Callable[[], Any]
    get_multi_account_mgr: Callable[[], Any]
    get_runtime_state: Callable[[], dict[str, Any]]
    logger: logging.Logger
    parse_proxy_setting: Callable[[str], tuple[str | None, str | None]]
    require_login: Callable[..., Callable]

def register_settings_routes(app: FastAPI, deps: SettingsRouteDeps) -> None:
    @app.get("/admin/settings", response_model=AdminSettingsPayload)
    @deps.require_login()
    async def admin_get_settings(request: Request):
        return get_settings_payload(deps.get_config())

    @app.put("/admin/settings", response_model=AdminSettingsPayload)
    @deps.require_login()
    async def admin_update_settings(
        request: Request,
        new_settings: AdminSettingsPayload = Body(...),
    ):
        try:
            return await update_settings(new_settings, deps)
        except ValueError as exc:
            deps.logger.error(f"[CONFIG] Settings validation failed: {exc}")
            raise HTTPException(400, f"Failed to validate settings: {exc}") from exc
        except Exception as exc:
            deps.logger.error(f"[CONFIG] Failed to update settings: {exc}")
            raise HTTPException(500, f"Failed to update settings: {exc}") from exc
