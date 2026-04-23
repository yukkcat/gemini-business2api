from __future__ import annotations

import logging
import os
from typing import Any, Callable, Protocol

from app.api.schemas.settings import (
    AdminSettingsPayload,
    BasicSettingsPayload,
    CfmailSettingsPayload,
    DuckmailSettingsPayload,
    FreemailSettingsPayload,
    GptmailSettingsPayload,
    ImageGenerationSettingsPayload,
    MoemailSettingsPayload,
    PublicDisplaySettingsPayload,
    QuotaLimitsSettingsPayload,
    RefreshSettingsPayload,
    RetrySettingsPayload,
    SessionSettingsPayload,
    VideoGenerationSettingsPayload,
)


class SettingsServiceDeps(Protocol):
    apply_runtime_state: Callable[[dict[str, Any]], None]
    build_retry_policy: Callable[[], Any]
    config_manager: Any
    create_http_client: Callable[[str | None], Any]
    get_config: Callable[[], Any]
    get_multi_account_mgr: Callable[[], Any]
    get_runtime_state: Callable[[], dict[str, Any]]
    logger: logging.Logger
    parse_proxy_setting: Callable[[str], tuple[str | None, str | None]]


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_copy(model: Any) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)
    return model.copy(deep=True)


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_browser_mode(browser_mode: str, browser_headless: bool) -> tuple[str, bool]:
    normalized = _clean_str(browser_mode).lower()
    if normalized not in {"normal", "silent", "headless"}:
        normalized = "headless" if browser_headless else "normal"
    return normalized, normalized == "headless"


def _normalize_temp_mail_provider(value: str) -> str:
    normalized = _clean_str(value).lower()
    if normalized in {"duckmail", "moemail", "freemail", "gptmail", "cfmail"}:
        return normalized
    return "duckmail"


def _normalize_image_output_format(value: str) -> str:
    return "url" if _clean_str(value).lower() == "url" else "base64"


def _normalize_video_output_format(value: str) -> str:
    normalized = _clean_str(value).lower()
    if normalized in {"url", "markdown"}:
        return normalized
    return "html"


def _normalize_string_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values or []:
        item = _clean_str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)

    return normalized


def _sanitize_settings_payload(payload: AdminSettingsPayload) -> AdminSettingsPayload:
    sanitized = _model_copy(payload)

    sanitized.basic.api_key = _clean_str(sanitized.basic.api_key)
    sanitized.basic.base_url = _clean_str(sanitized.basic.base_url)
    sanitized.basic.proxy_for_chat = _clean_str(sanitized.basic.proxy_for_chat)

    sanitized.retry.rate_limit_cooldown_seconds = sanitized.retry.text_rate_limit_cooldown_seconds

    sanitized.public_display.logo_url = _clean_str(sanitized.public_display.logo_url)
    sanitized.public_display.chat_url = _clean_str(sanitized.public_display.chat_url)

    sanitized.image_generation.supported_models = _normalize_string_list(
        sanitized.image_generation.supported_models
    )
    sanitized.image_generation.output_format = _normalize_image_output_format(
        sanitized.image_generation.output_format
    )
    sanitized.video_generation.output_format = _normalize_video_output_format(
        sanitized.video_generation.output_format
    )

    refresh = sanitized.refresh_settings
    refresh.proxy_for_auth = _clean_str(refresh.proxy_for_auth)
    refresh.temp_mail_provider = _normalize_temp_mail_provider(refresh.temp_mail_provider)
    refresh.browser_mode, refresh.browser_headless = _normalize_browser_mode(
        refresh.browser_mode,
        refresh.browser_headless,
    )
    refresh.register_domain = _clean_str(refresh.register_domain)
    refresh.scheduled_refresh_cron = _clean_str(refresh.scheduled_refresh_cron)

    refresh.duckmail.base_url = _clean_str(refresh.duckmail.base_url)
    refresh.duckmail.api_key = _clean_str(refresh.duckmail.api_key)

    refresh.moemail.base_url = _clean_str(refresh.moemail.base_url)
    refresh.moemail.api_key = _clean_str(refresh.moemail.api_key)
    refresh.moemail.domain = _clean_str(refresh.moemail.domain)

    refresh.freemail.base_url = _clean_str(refresh.freemail.base_url)
    refresh.freemail.jwt_token = _clean_str(refresh.freemail.jwt_token)
    refresh.freemail.domain = _clean_str(refresh.freemail.domain)

    refresh.gptmail.base_url = _clean_str(refresh.gptmail.base_url)
    refresh.gptmail.api_key = _clean_str(refresh.gptmail.api_key)
    refresh.gptmail.domain = _clean_str(refresh.gptmail.domain)

    refresh.cfmail.base_url = _clean_str(refresh.cfmail.base_url)
    refresh.cfmail.api_key = _clean_str(refresh.cfmail.api_key)
    refresh.cfmail.domain = _clean_str(refresh.cfmail.domain)

    return sanitized


def _build_refresh_settings(current_config: Any) -> RefreshSettingsPayload:
    basic = current_config.basic
    retry = current_config.retry
    browser_mode, browser_headless = _normalize_browser_mode(
        basic.browser_mode,
        basic.browser_headless,
    )

    return RefreshSettingsPayload(
        proxy_for_auth=basic.proxy_for_auth,
        duckmail=DuckmailSettingsPayload(
            base_url=basic.duckmail_base_url,
            api_key=basic.duckmail_api_key,
            verify_ssl=basic.duckmail_verify_ssl,
        ),
        temp_mail_provider=basic.temp_mail_provider,
        moemail=MoemailSettingsPayload(
            base_url=basic.moemail_base_url,
            api_key=basic.moemail_api_key,
            domain=basic.moemail_domain,
        ),
        freemail=FreemailSettingsPayload(
            base_url=basic.freemail_base_url,
            jwt_token=basic.freemail_jwt_token,
            verify_ssl=basic.freemail_verify_ssl,
            domain=basic.freemail_domain,
        ),
        mail_proxy_enabled=basic.mail_proxy_enabled,
        gptmail=GptmailSettingsPayload(
            base_url=basic.gptmail_base_url,
            api_key=basic.gptmail_api_key,
            verify_ssl=basic.gptmail_verify_ssl,
            domain=basic.gptmail_domain,
        ),
        cfmail=CfmailSettingsPayload(
            base_url=basic.cfmail_base_url,
            api_key=basic.cfmail_api_key,
            verify_ssl=basic.cfmail_verify_ssl,
            domain=basic.cfmail_domain,
        ),
        browser_mode=browser_mode,
        browser_headless=browser_headless,
        refresh_window_hours=basic.refresh_window_hours,
        register_domain=basic.register_domain,
        register_default_count=basic.register_default_count,
        auto_refresh_accounts_seconds=retry.auto_refresh_accounts_seconds,
        scheduled_refresh_enabled=retry.scheduled_refresh_enabled,
        scheduled_refresh_interval_minutes=retry.scheduled_refresh_interval_minutes,
        scheduled_refresh_cron=retry.scheduled_refresh_cron,
        verification_code_resend_count=retry.verification_code_resend_count,
        refresh_batch_size=retry.refresh_batch_size,
        refresh_batch_interval_minutes=retry.refresh_batch_interval_minutes,
        refresh_cooldown_hours=retry.refresh_cooldown_hours,
        delete_expired_accounts=retry.delete_expired_accounts,
        auto_register_enabled=retry.auto_register_enabled,
        min_account_count=retry.min_account_count,
    )


def get_settings_payload(current_config: Any) -> AdminSettingsPayload:
    return AdminSettingsPayload(
        basic=BasicSettingsPayload(
            api_key=current_config.basic.api_key,
            base_url=current_config.basic.base_url,
            proxy_for_chat=current_config.basic.proxy_for_chat,
            image_expire_hours=current_config.basic.image_expire_hours,
        ),
        retry=RetrySettingsPayload(
            max_account_switch_tries=current_config.retry.max_account_switch_tries,
            rate_limit_cooldown_seconds=current_config.retry.rate_limit_cooldown_seconds,
            text_rate_limit_cooldown_seconds=current_config.retry.text_rate_limit_cooldown_seconds,
            images_rate_limit_cooldown_seconds=current_config.retry.images_rate_limit_cooldown_seconds,
            videos_rate_limit_cooldown_seconds=current_config.retry.videos_rate_limit_cooldown_seconds,
            session_cache_ttl_seconds=current_config.retry.session_cache_ttl_seconds,
        ),
        public_display=PublicDisplaySettingsPayload(
            logo_url=current_config.public_display.logo_url,
            chat_url=current_config.public_display.chat_url,
        ),
        image_generation=ImageGenerationSettingsPayload(
            enabled=current_config.image_generation.enabled,
            supported_models=current_config.image_generation.supported_models,
            output_format=current_config.image_generation.output_format,
        ),
        video_generation=VideoGenerationSettingsPayload(
            output_format=current_config.video_generation.output_format,
        ),
        session=SessionSettingsPayload(
            expire_hours=current_config.session.expire_hours,
        ),
        refresh_settings=_build_refresh_settings(current_config),
        quota_limits=QuotaLimitsSettingsPayload(
            enabled=current_config.quota_limits.enabled,
            text_daily_limit=current_config.quota_limits.text_daily_limit,
            images_daily_limit=current_config.quota_limits.images_daily_limit,
            videos_daily_limit=current_config.quota_limits.videos_daily_limit,
        ),
    )


def _build_storage_snapshot(payload: AdminSettingsPayload) -> dict[str, Any]:
    sanitized = _sanitize_settings_payload(payload)
    refresh = _model_copy(sanitized.refresh_settings)
    browser_mode, browser_headless = _normalize_browser_mode(
        refresh.browser_mode,
        refresh.browser_headless,
    )
    refresh.browser_mode = browser_mode
    refresh.browser_headless = browser_headless

    snapshot = _model_dump(sanitized)
    snapshot["basic"] = _model_dump(sanitized.basic)
    snapshot["retry"] = _model_dump(sanitized.retry)
    snapshot["refresh_settings"] = _model_dump(refresh)
    return snapshot


def _apply_runtime_no_proxy(no_proxy_chat: str | None) -> None:
    no_proxy = ",".join(filter(None, {no_proxy_chat}))
    if no_proxy:
        os.environ["NO_PROXY"] = no_proxy
        return
    os.environ.pop("NO_PROXY", None)


async def update_settings(payload: AdminSettingsPayload, deps: SettingsServiceDeps) -> AdminSettingsPayload:
    runtime_state = deps.get_runtime_state()
    old_proxy_for_chat = runtime_state["proxy_for_chat"]
    old_retry_policy = runtime_state["retry_policy"]
    old_session_cache_ttl_seconds = runtime_state["session_cache_ttl_seconds"]

    snapshot = _build_storage_snapshot(payload)
    deps.config_manager.save_settings_snapshot(snapshot)
    deps.config_manager.reload()

    current_config = deps.get_config()
    new_runtime_state = dict(runtime_state)
    proxy_for_chat, no_proxy_chat = deps.parse_proxy_setting(current_config.basic.proxy_for_chat)
    new_runtime_state.update(
        {
            "api_key": current_config.basic.api_key,
            "proxy_for_chat": proxy_for_chat,
            "base_url": current_config.basic.base_url,
            "logo_url": current_config.public_display.logo_url,
            "chat_url": current_config.public_display.chat_url,
            "image_generation_enabled": current_config.image_generation.enabled,
            "image_generation_models": current_config.image_generation.supported_models,
            "max_account_switch_tries": current_config.retry.max_account_switch_tries,
            "retry_policy": deps.build_retry_policy(),
            "session_cache_ttl_seconds": current_config.retry.session_cache_ttl_seconds,
            "session_expire_hours": current_config.session.expire_hours,
        }
    )

    _apply_runtime_no_proxy(no_proxy_chat)

    if old_proxy_for_chat != new_runtime_state["proxy_for_chat"]:
        deps.logger.info("[CONFIG] Proxy configuration changed, rebuilding HTTP clients")
        await runtime_state["http_client"].aclose()
        await runtime_state["http_client_chat"].aclose()
        new_runtime_state["http_client"] = deps.create_http_client(new_runtime_state["proxy_for_chat"])
        new_runtime_state["http_client_chat"] = deps.create_http_client(new_runtime_state["proxy_for_chat"])
        deps.get_multi_account_mgr().update_http_client(new_runtime_state["http_client"])

    retry_policy = new_runtime_state["retry_policy"]
    retry_changed = (
        old_retry_policy.cooldowns.text != retry_policy.cooldowns.text
        or old_retry_policy.cooldowns.images != retry_policy.cooldowns.images
        or old_retry_policy.cooldowns.videos != retry_policy.cooldowns.videos
        or old_session_cache_ttl_seconds != new_runtime_state["session_cache_ttl_seconds"]
    )

    if retry_changed:
        deps.logger.info("[CONFIG] Retry policy changed, updating account managers")
        multi_account_mgr = deps.get_multi_account_mgr()
        multi_account_mgr.cache_ttl = new_runtime_state["session_cache_ttl_seconds"]
        for account_mgr in multi_account_mgr.accounts.values():
            account_mgr.apply_retry_policy(retry_policy)

    deps.apply_runtime_state(new_runtime_state)
    deps.logger.info("[CONFIG] Settings updated successfully")
    return get_settings_payload(current_config)
