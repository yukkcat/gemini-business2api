"""
Simplified configuration for the refresh worker.

Only includes refresh-related fields from BasicConfig and RetryConfig.
Loads from storage backend via storage.load_settings_sync().
"""

import os
import logging
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from worker import storage

load_dotenv()

logger = logging.getLogger(__name__)


def _parse_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


def _normalize_browser_mode(value, default: str = "normal") -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("normal", "silent", "headless"):
            return lowered
    return default


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _set_if_present(target: dict, key: str, value) -> None:
    if value is not None:
        target[key] = value


def _merge_mail_settings(target: dict, prefix: str, source: dict) -> None:
    if not source:
        return
    _set_if_present(target, f"{prefix}_base_url", source.get("base_url"))
    _set_if_present(target, f"{prefix}_api_key", source.get("api_key"))
    _set_if_present(target, f"{prefix}_verify_ssl", source.get("verify_ssl"))
    _set_if_present(target, f"{prefix}_domain", source.get("domain"))


def _normalize_loaded_settings(raw_data: dict) -> dict:
    """Accept both direct storage snapshots and /admin/settings payloads."""
    data = _as_dict(raw_data)
    basic = dict(_as_dict(data.get("basic")))
    retry = dict(_as_dict(data.get("retry")))
    refresh = _as_dict(data.get("refresh_settings"))

    if refresh:
        for key in (
            "proxy_for_auth",
            "temp_mail_provider",
            "mail_proxy_enabled",
            "browser_mode",
            "browser_headless",
            "refresh_window_hours",
            "register_domain",
            "register_default_count",
        ):
            _set_if_present(basic, key, refresh.get(key))
        _merge_mail_settings(basic, "duckmail", _as_dict(refresh.get("duckmail")))
        _merge_mail_settings(basic, "moemail", _as_dict(refresh.get("moemail")))
        _merge_mail_settings(basic, "gptmail", _as_dict(refresh.get("gptmail")))
        _merge_mail_settings(basic, "cfmail", _as_dict(refresh.get("cfmail")))

        freemail = _as_dict(refresh.get("freemail"))
        if freemail:
            _set_if_present(basic, "freemail_base_url", freemail.get("base_url"))
            _set_if_present(basic, "freemail_jwt_token", freemail.get("jwt_token"))
            _set_if_present(basic, "freemail_verify_ssl", freemail.get("verify_ssl"))
            _set_if_present(basic, "freemail_domain", freemail.get("domain"))

        for key in (
            "scheduled_refresh_enabled",
            "scheduled_refresh_interval_minutes",
            "scheduled_refresh_cron",
            "verification_code_resend_count",
            "refresh_batch_size",
            "refresh_batch_interval_minutes",
            "refresh_cooldown_hours",
            "delete_expired_accounts",
            "auto_register_enabled",
            "min_account_count",
        ):
            if refresh.get(key) is not None:
                retry[key] = refresh[key]

    return {"basic": basic, "retry": retry}


# ==================== Config models ====================

class BasicConfig(BaseModel):
    """Refresh-related basic config"""
    proxy_for_auth: str = Field(default="", description="账户操作代理地址")
    duckmail_base_url: str = Field(default="https://api.duckmail.sbs", description="DuckMail API地址")
    duckmail_api_key: str = Field(default="", description="DuckMail API key")
    duckmail_verify_ssl: bool = Field(default=True, description="DuckMail SSL校验")
    temp_mail_provider: str = Field(default="duckmail", description="临时邮箱提供商")
    moemail_base_url: str = Field(default="https://moemail.nanohajimi.mom", description="Moemail API地址")
    moemail_api_key: str = Field(default="", description="Moemail API key")
    moemail_domain: str = Field(default="", description="Moemail 邮箱域名")
    freemail_base_url: str = Field(default="http://your-freemail-server.com", description="Freemail API地址")
    freemail_jwt_token: str = Field(default="", description="Freemail JWT Token")
    freemail_verify_ssl: bool = Field(default=True, description="Freemail SSL校验")
    freemail_domain: str = Field(default="", description="Freemail 邮箱域名")
    mail_proxy_enabled: bool = Field(default=False, description="是否启用临时邮箱代理")
    gptmail_base_url: str = Field(default="https://mail.chatgpt.org.uk", description="GPTMail API地址")
    gptmail_api_key: str = Field(default="gpt-test", description="GPTMail API key")
    gptmail_verify_ssl: bool = Field(default=True, description="GPTMail SSL校验")
    gptmail_domain: str = Field(default="", description="GPTMail 邮箱域名")
    cfmail_base_url: str = Field(default="", description="CFMail API地址")
    cfmail_api_key: str = Field(default="", description="CFMail API key")
    cfmail_verify_ssl: bool = Field(default=True, description="CFMail SSL校验")
    cfmail_domain: str = Field(default="", description="CFMail 邮箱域名")
    browser_mode: str = Field(default="normal", description="浏览器模式：normal / silent / headless")
    browser_headless: bool = Field(default=False, description="兼容字段：是否无头模式")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="过期刷新窗口（小时）")
    register_domain: str = Field(default="", description="注册账号使用的邮箱域名（DuckMail专用）")
    register_default_count: int = Field(default=20, ge=1, description="默认注册账号数量")


class RetryConfig(BaseModel):
    """Refresh-related retry config"""
    scheduled_refresh_enabled: bool = Field(default=False, description="是否启用定时刷新任务")
    scheduled_refresh_cron: str = Field(default="08:00,20:00", description="刷新时间，如 '08:00,20:00' 或 '*/120'(每120分钟)")
    verification_code_resend_count: int = Field(default=2, ge=0, le=5, description="verification code resend attempts")
    refresh_batch_size: int = Field(default=5, ge=1, le=20, description="每批刷新账号数")
    refresh_batch_interval_minutes: int = Field(default=30, ge=5, le=120, description="批次间等待时间(分钟)")
    refresh_cooldown_hours: float = Field(default=12.0, ge=1, le=48, description="同一账号刷新冷却期(小时)")
    scheduled_refresh_interval_minutes: int = Field(default=0, ge=0, le=720, description="(旧字段，已废弃) 定时刷新检测间隔")
    delete_expired_accounts: bool = Field(default=False, description="是否自动删除过期账号")
    auto_register_enabled: bool = Field(default=False, description="是否启用账号不足时自动注册")
    min_account_count: int = Field(default=0, ge=0, le=100, description="最低账号数量，低于此值时自动注册补充")


class WorkerConfig(BaseModel):
    """Worker configuration (aggregates basic + retry)"""
    basic: BasicConfig
    retry: RetryConfig


# ==================== Config Manager ====================

class ConfigManager:
    """Configuration manager for the refresh worker (singleton)."""

    def __init__(self):
        self._config: Optional[WorkerConfig] = None
        self.load()

    def load(self):
        """Load config from storage backend."""
        yaml_data = _normalize_loaded_settings(self._load_from_db())

        basic_data = yaml_data.get("basic", {})

        # Compat: migrate old proxy field
        old_proxy = basic_data.get("proxy", "")
        old_proxy_for_auth_bool = basic_data.get("proxy_for_auth")
        proxy_for_auth = basic_data.get("proxy_for_auth", "")
        if not proxy_for_auth and old_proxy:
            if isinstance(old_proxy_for_auth_bool, bool) and old_proxy_for_auth_bool:
                proxy_for_auth = old_proxy

        legacy_headless = _parse_bool(basic_data.get("browser_headless"), False)
        default_browser_mode = "headless" if legacy_headless else "normal"
        browser_mode = _normalize_browser_mode(basic_data.get("browser_mode"), default_browser_mode)
        browser_headless = browser_mode == "headless"

        basic_config = BasicConfig(
            proxy_for_auth=str(proxy_for_auth or "").strip(),
            duckmail_base_url=basic_data.get("duckmail_base_url") or "https://api.duckmail.sbs",
            duckmail_api_key=str(basic_data.get("duckmail_api_key") or "").strip(),
            duckmail_verify_ssl=_parse_bool(basic_data.get("duckmail_verify_ssl"), True),
            temp_mail_provider=basic_data.get("temp_mail_provider") or "duckmail",
            moemail_base_url=basic_data.get("moemail_base_url") or "https://moemail.nanohajimi.mom",
            moemail_api_key=str(basic_data.get("moemail_api_key") or "").strip(),
            moemail_domain=str(basic_data.get("moemail_domain") or "").strip(),
            freemail_base_url=basic_data.get("freemail_base_url") or "http://your-freemail-server.com",
            freemail_jwt_token=str(basic_data.get("freemail_jwt_token") or "").strip(),
            freemail_verify_ssl=_parse_bool(basic_data.get("freemail_verify_ssl"), True),
            freemail_domain=str(basic_data.get("freemail_domain") or "").strip(),
            mail_proxy_enabled=_parse_bool(basic_data.get("mail_proxy_enabled"), False),
            gptmail_base_url=str(basic_data.get("gptmail_base_url") or "https://mail.chatgpt.org.uk").strip(),
            gptmail_api_key=str(basic_data.get("gptmail_api_key") or "").strip(),
            gptmail_verify_ssl=_parse_bool(basic_data.get("gptmail_verify_ssl"), True),
            gptmail_domain=str(basic_data.get("gptmail_domain") or "").strip(),
            cfmail_base_url=str(basic_data.get("cfmail_base_url") or "").strip(),
            cfmail_api_key=str(basic_data.get("cfmail_api_key") or "").strip(),
            cfmail_verify_ssl=_parse_bool(basic_data.get("cfmail_verify_ssl"), True),
            cfmail_domain=str(basic_data.get("cfmail_domain") or "").strip(),
            browser_mode=browser_mode,
            browser_headless=browser_headless,
            refresh_window_hours=int(basic_data.get("refresh_window_hours", 1)),
            register_domain=str(basic_data.get("register_domain") or "").strip(),
            register_default_count=max(1, int(basic_data.get("register_default_count", 20))),
        )

        try:
            retry_config = RetryConfig(**yaml_data.get("retry", {}))
        except Exception as e:
            logger.warning(f"[WARN] Retry config load failed, using defaults: {e}")
            retry_config = RetryConfig()

        self._config = WorkerConfig(basic=basic_config, retry=retry_config)

    def _load_from_db(self) -> dict:
        """Load config from storage backend (database or remote project)."""
        if storage.is_database_enabled():
            try:
                data = storage.load_settings_sync()
                if data is None:
                    mode = storage.get_storage_mode()
                    if mode == "remote":
                        raise RuntimeError("Remote project settings unavailable")
                    logger.warning("[WARN] No settings found (empty DB or connection issue), using defaults")
                    return {}
                if isinstance(data, dict):
                    return data
                return {}
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"[ERROR] Database load failed: {e}")
                raise RuntimeError(f"Database load failed: {e}")

        logger.error("[ERROR] Database not enabled")
        raise RuntimeError("DATABASE_URL or REMOTE_PROJECT_BASE_URL not configured, worker cannot start")

    def reload(self):
        """Hot-reload config from storage backend."""
        self.load()

    @property
    def config(self) -> WorkerConfig:
        return self._config


# ==================== Global singleton ====================

config_manager = ConfigManager()


class _ConfigProxy:
    """Config proxy that always returns the latest config."""
    @property
    def basic(self):
        return config_manager.config.basic

    @property
    def retry(self):
        return config_manager.config.retry


config = _ConfigProxy()
