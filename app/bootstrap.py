from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request

from app.api.routers import (
    AccountRouteDeps,
    ChatRouteDeps,
    DashboardRouteDeps,
    GalleryRouteDeps,
    ImageRouteDeps,
    LogRouteDeps,
    PublicRouteDeps,
    SettingsRouteDeps,
    SystemRouteDeps,
    register_account_routes,
    register_chat_routes,
    register_dashboard_routes,
    register_gallery_routes,
    register_image_routes,
    register_log_routes,
    register_public_routes,
    register_settings_routes,
    register_system_routes,
)


@dataclass(frozen=True)
class RouteBootstrapDeps:
    api_key: Callable[[], str]
    admin_key: Callable[[], str]
    apply_runtime_state: Callable[[dict[str, Any]], None]
    build_retry_policy: Callable[[], Any]
    bulk_delete_accounts: Callable[..., tuple[Any, int, list[str]]]
    bulk_update_account_disabled_status: Callable[[list[str], bool, Any], tuple[int, list[str]]]
    chat_handler: Callable[..., Awaitable[dict[str, Any]]]
    config_manager: Any
    create_http_client: Callable[[str | None], Any]
    delete_account: Callable[..., Any]
    format_account_expiration: Callable[[Any], tuple[str, str, str]]
    get_config: Callable[[], Any]
    get_base_url: Callable[[Request], str]
    get_global_stats: Callable[[], dict[str, Any]]
    get_http_client: Callable[[], Any]
    get_log_buffer: Callable[[], Any]
    get_model_ids: Callable[[], list[str]]
    get_multi_account_mgr: Callable[[], Any]
    get_retry_policy: Callable[[], Any]
    get_runtime_state: Callable[[], dict[str, Any]]
    get_sanitized_logs: Callable[[int], list[dict[str, Any]]]
    get_session_cache_ttl_seconds: Callable[[], int]
    get_update_status: Callable[[], Any]
    get_user_agent: Callable[[], str]
    get_version_info: Callable[[], Any]
    image_dir: str
    load_accounts_from_source: Callable[[], list[Any]]
    logger: logging.Logger
    log_lock: Any
    login_user: Callable[[Request], None]
    logout_user: Callable[[Request], None]
    parse_proxy_setting: Callable[[str], tuple[str | None, str | None]]
    require_login: Callable[..., Callable]
    save_account_cooldown_state: Callable[[str, Any], Awaitable[Any]]
    save_image_file: Callable[[bytes, str, str, str, str, str], str]
    save_stats: Callable[[dict[str, Any]], Awaitable[None]]
    scan_media_files: Callable[[], list[dict[str, Any]]]
    set_multi_account_mgr: Callable[[Any], None]
    stats_db: Any
    stats_lock: Any
    update_account_disabled_status: Callable[[str, bool, Any], Any]
    update_accounts_config: Callable[..., Any]
    uptime_tracker: Any
    verify_api_key: Callable[[str, str | None], Any]
    video_dir: str


def register_http_routes(app: FastAPI, deps: RouteBootstrapDeps) -> None:
    register_chat_routes(
        app,
        ChatRouteDeps(
            api_key=deps.api_key,
            chat_handler=deps.chat_handler,
            get_model_ids=deps.get_model_ids,
            verify_api_key=deps.verify_api_key,
        ),
    )

    register_dashboard_routes(
        app,
        DashboardRouteDeps(
            get_multi_account_mgr=deps.get_multi_account_mgr,
            require_login=deps.require_login,
            stats_db=deps.stats_db,
        ),
    )

    register_system_routes(
        app,
        SystemRouteDeps(
            admin_key=deps.admin_key,
            get_multi_account_mgr=deps.get_multi_account_mgr,
            get_update_status=deps.get_update_status,
            logger=deps.logger,
            login_user=deps.login_user,
            logout_user=deps.logout_user,
            require_login=deps.require_login,
            stats_db=deps.stats_db,
        ),
    )

    register_public_routes(
        app,
        PublicRouteDeps(
            get_config=deps.get_config,
            get_global_stats=deps.get_global_stats,
            get_sanitized_logs=deps.get_sanitized_logs,
            get_version_info=deps.get_version_info,
            logger=deps.logger,
            save_stats=deps.save_stats,
            stats_lock=deps.stats_lock,
            uptime_tracker=deps.uptime_tracker,
        ),
    )

    register_log_routes(
        app,
        LogRouteDeps(
            get_log_buffer=deps.get_log_buffer,
            log_lock=deps.log_lock,
            logger=deps.logger,
            require_login=deps.require_login,
        ),
    )

    register_gallery_routes(
        app,
        GalleryRouteDeps(
            get_config=deps.get_config,
            image_dir=deps.image_dir,
            logger=deps.logger,
            require_login=deps.require_login,
            scan_media_files=deps.scan_media_files,
            video_dir=deps.video_dir,
        ),
    )

    register_image_routes(
        app,
        ImageRouteDeps(
            api_key=deps.api_key,
            chat_handler=deps.chat_handler,
            config_manager=deps.config_manager,
            get_base_url=deps.get_base_url,
            get_http_client=deps.get_http_client,
            image_dir=deps.image_dir,
            logger=deps.logger,
            save_image_file=deps.save_image_file,
            verify_api_key=deps.verify_api_key,
        ),
    )

    register_account_routes(
        app,
        AccountRouteDeps(
            bulk_delete_accounts=deps.bulk_delete_accounts,
            bulk_update_account_disabled_status=deps.bulk_update_account_disabled_status,
            delete_account=deps.delete_account,
            format_account_expiration=deps.format_account_expiration,
            get_global_stats=deps.get_global_stats,
            get_http_client=deps.get_http_client,
            get_multi_account_mgr=deps.get_multi_account_mgr,
            get_retry_policy=deps.get_retry_policy,
            get_session_cache_ttl_seconds=deps.get_session_cache_ttl_seconds,
            get_user_agent=deps.get_user_agent,
            load_accounts_from_source=deps.load_accounts_from_source,
            logger=deps.logger,
            require_login=deps.require_login,
            save_account_cooldown_state=deps.save_account_cooldown_state,
            set_multi_account_mgr=deps.set_multi_account_mgr,
            update_account_disabled_status=deps.update_account_disabled_status,
            update_accounts_config=deps.update_accounts_config,
        ),
    )

    register_settings_routes(
        app,
        SettingsRouteDeps(
            apply_runtime_state=deps.apply_runtime_state,
            build_retry_policy=deps.build_retry_policy,
            config_manager=deps.config_manager,
            create_http_client=deps.create_http_client,
            get_config=deps.get_config,
            get_multi_account_mgr=deps.get_multi_account_mgr,
            get_runtime_state=deps.get_runtime_state,
            logger=deps.logger,
            parse_proxy_setting=deps.parse_proxy_setting,
            require_login=deps.require_login,
        ),
    )
