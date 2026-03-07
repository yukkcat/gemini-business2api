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


# ==================== Config models ====================

class BasicConfig(BaseModel):
    """Refresh-related basic config"""
    proxy_for_auth: str = Field(default="", description="账户操作代理地址")
    duckmail_base_url: str = Field(default="https://api.duckmail.sbs", description="DuckMail API地址")
    duckmail_api_key: str = Field(default="", description="DuckMail API key")
    duckmail_verify_ssl: bool = Field(default=True, description="DuckMail SSL校验")
    temp_mail_provider: str = Field(default="moemail", description="临时邮箱提供商")
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
    browser_mode: str = Field(default="normal", description="浏览器模式：normal / silent / headless")
    browser_headless: bool = Field(default=False, description="兼容字段：是否无头模式")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="过期刷新窗口（小时）")
    register_domain: str = Field(default="", description="注册账号使用的邮箱域名（DuckMail专用）")
    register_default_count: int = Field(default=1, ge=1, le=20, description="默认注册账号数量")


class RetryConfig(BaseModel):
    """Refresh-related retry config"""
    scheduled_refresh_enabled: bool = Field(default=False, description="是否启用定时刷新任务")
    scheduled_refresh_cron: str = Field(default="08:00,20:00", description="刷新时间，如 '08:00,20:00' 或 '*/120'(每120分钟)")
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
        yaml_data = self._load_from_db()

        basic_data = yaml_data.get("basic", {})
        storage_mode = storage.get_storage_mode()

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
            temp_mail_provider=basic_data.get("temp_mail_provider") or "moemail",
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
            browser_mode=browser_mode,
            browser_headless=browser_headless,
            refresh_window_hours=int(basic_data.get("refresh_window_hours", 1)),
            register_domain=str(basic_data.get("register_domain") or "").strip(),
            register_default_count=max(1, int(basic_data.get("register_default_count", 1))),
        )

        # Remote mode safe default:
        # Do not blindly reuse remote project's proxy_for_auth on local worker,
        # because remote-side localhost proxies (e.g. 127.0.0.1:7890) are usually
        # unreachable from this machine and can cause "cannot access Google".
        use_remote_proxy = _parse_bool(os.getenv("REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH"), False)
        if storage_mode == "remote" and os.getenv("PROXY_FOR_AUTH") is None and not use_remote_proxy:
            if basic_config.proxy_for_auth:
                logger.warning(
                    "[CONFIG] remote mode: ignoring remote proxy_for_auth=%s; set local PROXY_FOR_AUTH to enable proxy",
                    basic_config.proxy_for_auth,
                )
            basic_config.proxy_for_auth = ""

        try:
            retry_config = RetryConfig(**yaml_data.get("retry", {}))
        except Exception as e:
            logger.warning(f"[WARN] Retry config load failed, using defaults: {e}")
            retry_config = RetryConfig()

        self._config = WorkerConfig(basic=basic_config, retry=retry_config)

        # Apply environment variable overrides (take precedence over storage values)
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Override config fields with environment variables when set."""
        env_refresh_enabled = os.getenv("FORCE_REFRESH_ENABLED")
        if env_refresh_enabled is not None:
            val = _parse_bool(env_refresh_enabled, self._config.retry.scheduled_refresh_enabled)
            self._config.retry.scheduled_refresh_enabled = val
            logger.info("[CONFIG] env override: FORCE_REFRESH_ENABLED=%s", val)

        env_interval = os.getenv("REFRESH_INTERVAL_MINUTES")
        if env_interval is not None:
            try:
                val = max(1, min(720, int(env_interval)))
                self._config.retry.scheduled_refresh_interval_minutes = val
                logger.info("[CONFIG] env override: REFRESH_INTERVAL_MINUTES=%d", val)
            except ValueError:
                logger.warning("[CONFIG] invalid REFRESH_INTERVAL_MINUTES=%r, ignored", env_interval)

        env_window = os.getenv("REFRESH_WINDOW_HOURS")
        if env_window is not None:
            try:
                val = max(0, min(24, int(env_window)))
                self._config.basic.refresh_window_hours = val
                logger.info("[CONFIG] env override: REFRESH_WINDOW_HOURS=%d", val)
            except ValueError:
                logger.warning("[CONFIG] invalid REFRESH_WINDOW_HOURS=%r, ignored", env_window)

        env_browser_mode = os.getenv("BROWSER_MODE")
        if env_browser_mode is not None:
            mode = _normalize_browser_mode(env_browser_mode, self._config.basic.browser_mode)
            if mode != env_browser_mode.strip().lower():
                logger.warning(
                    "[CONFIG] invalid BROWSER_MODE=%r, fallback to %s",
                    env_browser_mode,
                    mode,
                )
            self._config.basic.browser_mode = mode
            self._config.basic.browser_headless = mode == "headless"
            logger.info("[CONFIG] env override: BROWSER_MODE=%s", mode)

        env_headless = os.getenv("BROWSER_HEADLESS")
        if env_headless is not None:
            if env_browser_mode is not None:
                logger.info("[CONFIG] BROWSER_HEADLESS ignored because BROWSER_MODE is set")
            else:
                val = _parse_bool(env_headless, self._config.basic.browser_headless)
                self._config.basic.browser_headless = val
                self._config.basic.browser_mode = "headless" if val else "normal"
                logger.info("[CONFIG] env override: BROWSER_HEADLESS=%s", val)

        env_proxy = os.getenv("PROXY_FOR_AUTH")
        if env_proxy is not None:
            self._config.basic.proxy_for_auth = env_proxy.strip()
            logger.info("[CONFIG] env override: PROXY_FOR_AUTH=%s", "***" if env_proxy.strip() else "(empty)")

        env_delete_expired = os.getenv("DELETE_EXPIRED_ACCOUNTS")
        if env_delete_expired is not None:
            val = _parse_bool(env_delete_expired, self._config.retry.delete_expired_accounts)
            self._config.retry.delete_expired_accounts = val
            logger.info("[CONFIG] env override: DELETE_EXPIRED_ACCOUNTS=%s", val)

        env_auto_register = os.getenv("AUTO_REGISTER_ENABLED")
        if env_auto_register is not None:
            val = _parse_bool(env_auto_register, self._config.retry.auto_register_enabled)
            self._config.retry.auto_register_enabled = val
            logger.info("[CONFIG] env override: AUTO_REGISTER_ENABLED=%s", val)

        env_min_count = os.getenv("MIN_ACCOUNT_COUNT")
        if env_min_count is not None:
            try:
                val = max(0, min(100, int(env_min_count)))
                self._config.retry.min_account_count = val
                logger.info("[CONFIG] env override: MIN_ACCOUNT_COUNT=%d", val)
            except ValueError:
                logger.warning("[CONFIG] invalid MIN_ACCOUNT_COUNT=%r, ignored", env_min_count)

        env_register_domain = os.getenv("REGISTER_DOMAIN")
        if env_register_domain is not None:
            self._config.basic.register_domain = env_register_domain.strip()
            logger.info("[CONFIG] env override: REGISTER_DOMAIN=%s", env_register_domain.strip() or "(empty)")

        env_register_count = os.getenv("REGISTER_DEFAULT_COUNT")
        if env_register_count is not None:
            try:
                val = max(1, min(20, int(env_register_count)))
                self._config.basic.register_default_count = val
                logger.info("[CONFIG] env override: REGISTER_DEFAULT_COUNT=%d", val)
            except ValueError:
                logger.warning("[CONFIG] invalid REGISTER_DEFAULT_COUNT=%r, ignored", env_register_count)

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
