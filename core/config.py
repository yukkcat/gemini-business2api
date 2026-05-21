"""
Unified configuration management.

Security configuration is read from environment variables only.
Business configuration is loaded from storage and can be hot reloaded.
"""

from __future__ import annotations

import os
import secrets
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator

from core import storage

load_dotenv()


def _parse_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _to_clean_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_browser_mode(browser_mode: object, browser_headless: object) -> tuple[str, bool]:
    headless = _parse_bool(browser_headless, False)
    default_mode = "headless" if headless else "normal"
    normalized = _to_clean_str(browser_mode, default_mode).lower()
    if normalized not in {"normal", "silent", "headless"}:
        normalized = default_mode
    return normalized, normalized == "headless"


def _normalize_temp_mail_provider(value: object, default: str = "duckmail") -> str:
    normalized = _to_clean_str(value, default).lower()
    if normalized not in {"duckmail", "moemail", "freemail", "gptmail", "cfmail"}:
        return default
    return normalized


IMAGE_MODEL_ALIASES = {
    "gemini-2.5-flash": "gemini-3.1-flash",
    "gemini-3-flash-preview": "gemini-3.1-flash",
}


def _normalize_model_list(values: object) -> List[str]:
    if not isinstance(values, list):
        return []

    normalized_models: List[str] = []
    seen: set[str] = set()
    for value in values:
        model = IMAGE_MODEL_ALIASES.get(_to_clean_str(value), _to_clean_str(value))
        if not model or model in seen:
            continue
        seen.add(model)
        normalized_models.append(model)

    return normalized_models


def _model_dump(model: BaseModel) -> dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _pick_defined(*values: object, default: object = None) -> object:
    for value in values:
        if value is not None:
            return value
    return default


STORAGE_BASIC_FIELDS = (
    "api_key",
    "base_url",
    "proxy_for_chat",
    "image_expire_hours",
)

STORAGE_RETRY_FIELDS = (
    "max_account_switch_tries",
    "rate_limit_cooldown_seconds",
    "text_rate_limit_cooldown_seconds",
    "images_rate_limit_cooldown_seconds",
    "videos_rate_limit_cooldown_seconds",
    "session_cache_ttl_seconds",
)


class BasicConfig(BaseModel):
    """Primary application settings."""

    api_key: str = Field(default="", description="API access key(s), comma separated")
    base_url: str = Field(default="", description="Public base URL")
    proxy_for_chat: str = Field(default="", description="Proxy used for chat/session traffic")
    proxy_for_auth: str = Field(default="", description="Proxy used for refresh/auth automation")
    image_expire_hours: int = Field(default=12, ge=-1, le=720, description="Media retention hours")

    duckmail_base_url: str = Field(default="https://api.duckmail.sbs", description="DuckMail base URL")
    duckmail_api_key: str = Field(default="", description="DuckMail API key")
    duckmail_verify_ssl: bool = Field(default=True, description="DuckMail SSL verification")

    temp_mail_provider: str = Field(default="duckmail", description="Default temp mail provider")

    moemail_base_url: str = Field(default="https://moemail.nanohajimi.mom", description="Moemail base URL")
    moemail_api_key: str = Field(default="", description="Moemail API key")
    moemail_domain: str = Field(default="", description="Moemail domain")

    freemail_base_url: str = Field(default="http://your-freemail-server.com", description="Freemail base URL")
    freemail_jwt_token: str = Field(default="", description="Freemail JWT token")
    freemail_verify_ssl: bool = Field(default=True, description="Freemail SSL verification")
    freemail_domain: str = Field(default="", description="Freemail domain")

    mail_proxy_enabled: bool = Field(default=False, description="Whether temp-mail requests use proxy")

    gptmail_base_url: str = Field(default="https://mail.chatgpt.org.uk", description="GPTMail base URL")
    gptmail_api_key: str = Field(default="", description="GPTMail API key")
    gptmail_verify_ssl: bool = Field(default=True, description="GPTMail SSL verification")
    gptmail_domain: str = Field(default="", description="GPTMail domain")

    cfmail_base_url: str = Field(default="", description="CFMail base URL")
    cfmail_api_key: str = Field(default="", description="CFMail API key")
    cfmail_verify_ssl: bool = Field(default=True, description="CFMail SSL verification")
    cfmail_domain: str = Field(default="", description="CFMail domain")

    browser_mode: str = Field(default="normal", description="normal / silent / headless")
    browser_headless: bool = Field(default=False, description="Legacy headless compatibility flag")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="Refresh window in hours")
    register_domain: str = Field(default="", description="Register domain")
    register_default_count: int = Field(default=20, ge=1, le=200, description="Default register count")

    @validator("temp_mail_provider")
    def validate_temp_mail_provider(cls, value: str) -> str:
        return _normalize_temp_mail_provider(value)

    @validator("browser_mode")
    def validate_browser_mode(cls, value: str) -> str:
        mode, _ = _normalize_browser_mode(value, value == "headless")
        return mode


class ImageGenerationConfig(BaseModel):
    """Image generation settings."""

    enabled: bool = Field(default=False, description="Enable image generation")
    supported_models: List[str] = Field(default=[], description="Models that support image generation")
    output_format: str = Field(default="base64", description="base64 or url")

    @validator("supported_models", pre=True)
    def validate_supported_models(cls, value: object) -> List[str]:
        return _normalize_model_list(value)

    @validator("output_format")
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"base64", "url"}:
            raise ValueError("output_format must be one of ['base64', 'url']")
        return normalized


class VideoGenerationConfig(BaseModel):
    """Video generation settings."""

    output_format: str = Field(default="url", description="html / url / markdown")

    @validator("output_format")
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"html", "url", "markdown"}:
            raise ValueError("output_format must be one of ['html', 'url', 'markdown']")
        return normalized


class RetryConfig(BaseModel):
    """Runtime retry and refresh automation settings."""

    max_account_switch_tries: int = Field(default=5, ge=1, le=20)
    rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=86400)
    text_rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=86400)
    images_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400)
    videos_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400)
    session_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400)

    auto_refresh_accounts_seconds: int = Field(default=60, ge=0, le=86400)
    scheduled_refresh_enabled: bool = Field(default=False)
    scheduled_refresh_interval_minutes: int = Field(default=30, ge=0, le=720)
    scheduled_refresh_cron: str = Field(default="", description="Legacy worker-compatible schedule syntax")
    verification_code_resend_count: int = Field(default=2, ge=0, le=5)
    refresh_batch_size: int = Field(default=5, ge=1, le=50)
    refresh_batch_interval_minutes: int = Field(default=30, ge=0, le=720)
    refresh_cooldown_hours: float = Field(default=12.0, ge=0, le=168)
    delete_expired_accounts: bool = Field(default=False)
    auto_register_enabled: bool = Field(default=False)
    min_account_count: int = Field(default=0, ge=0, le=1000)


class QuotaLimitsConfig(BaseModel):
    """Daily quota limit settings."""

    enabled: bool = Field(default=True)
    text_daily_limit: int = Field(default=200, ge=0, le=999999)
    images_daily_limit: int = Field(default=10, ge=0, le=999999)
    videos_daily_limit: int = Field(default=3, ge=0, le=999999)


class PublicDisplayConfig(BaseModel):
    """Public branding/display settings."""

    logo_url: str = Field(default="", description="Logo URL")
    chat_url: str = Field(default="", description="Chat entry URL")


class SessionConfig(BaseModel):
    """Admin session settings."""

    expire_hours: int = Field(default=24, ge=1, le=168)


class SecurityConfig(BaseModel):
    """Security settings read from environment only."""

    admin_key: str = Field(default="", description="Admin password")
    session_secret_key: str = Field(..., description="Session signing secret")


class AppConfig(BaseModel):
    """Full application configuration."""

    security: SecurityConfig
    basic: BasicConfig
    image_generation: ImageGenerationConfig
    video_generation: VideoGenerationConfig = Field(default_factory=VideoGenerationConfig)
    retry: RetryConfig
    quota_limits: QuotaLimitsConfig = Field(default_factory=QuotaLimitsConfig)
    public_display: PublicDisplayConfig
    session: SessionConfig


class ConfigManager:
    """Central config manager."""

    def __init__(self, yaml_path: str | None = None):
        self.yaml_path = yaml_path or ""
        self._config: Optional[AppConfig] = None
        self.load()

    def load(self) -> None:
        yaml_data = self._load_yaml()
        security_config = SecurityConfig(
            admin_key=os.getenv("ADMIN_KEY", ""),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret()),
        )

        basic_data = self._build_runtime_basic_data(yaml_data)
        basic_config = self._build_basic_config(basic_data)

        try:
            image_generation_config = ImageGenerationConfig(**dict(yaml_data.get("image_generation", {}) or {}))
        except Exception as exc:
            print(f"[WARN] image_generation config load failed, using defaults: {exc}")
            image_generation_config = ImageGenerationConfig()

        try:
            video_generation_config = VideoGenerationConfig(**dict(yaml_data.get("video_generation", {}) or {}))
        except Exception as exc:
            print(f"[WARN] video_generation config load failed, using defaults: {exc}")
            video_generation_config = VideoGenerationConfig()

        try:
            retry_config = self._build_retry_config(self._build_runtime_retry_data(yaml_data))
        except Exception as exc:
            print(f"[WARN] retry config load failed, using defaults: {exc}")
            retry_config = RetryConfig()

        try:
            quota_limits_config = QuotaLimitsConfig(**dict(yaml_data.get("quota_limits", {}) or {}))
        except Exception as exc:
            print(f"[WARN] quota_limits config load failed, using defaults: {exc}")
            quota_limits_config = QuotaLimitsConfig()

        try:
            public_display_config = PublicDisplayConfig(**dict(yaml_data.get("public_display", {}) or {}))
        except Exception as exc:
            print(f"[WARN] public_display config load failed, using defaults: {exc}")
            public_display_config = PublicDisplayConfig()

        try:
            session_config = SessionConfig(**dict(yaml_data.get("session", {}) or {}))
        except Exception as exc:
            print(f"[WARN] session config load failed, using defaults: {exc}")
            session_config = SessionConfig()

        self._config = AppConfig(
            security=security_config,
            basic=basic_config,
            image_generation=image_generation_config,
            video_generation=video_generation_config,
            retry=retry_config,
            quota_limits=quota_limits_config,
            public_display=public_display_config,
            session=session_config,
        )

    def _build_basic_config(self, basic_data: dict[str, object]) -> BasicConfig:
        old_proxy = _to_clean_str(basic_data.get("proxy"))

        proxy_for_chat_raw = basic_data.get("proxy_for_chat", "")
        if isinstance(proxy_for_chat_raw, bool):
            proxy_for_chat = old_proxy if proxy_for_chat_raw else ""
        else:
            proxy_for_chat = _to_clean_str(proxy_for_chat_raw)
            if not proxy_for_chat and old_proxy and "proxy_for_chat" not in basic_data:
                proxy_for_chat = old_proxy

        proxy_for_auth_raw = basic_data.get("proxy_for_auth", "")
        if isinstance(proxy_for_auth_raw, bool):
            proxy_for_auth = old_proxy if proxy_for_auth_raw else ""
        else:
            proxy_for_auth = _to_clean_str(proxy_for_auth_raw)
            if not proxy_for_auth and old_proxy and "proxy_for_auth" not in basic_data:
                proxy_for_auth = old_proxy

        browser_mode, browser_headless = _normalize_browser_mode(
            basic_data.get("browser_mode"),
            basic_data.get("browser_headless"),
        )

        return BasicConfig(
            api_key=_to_clean_str(basic_data.get("api_key")),
            base_url=_to_clean_str(basic_data.get("base_url")),
            proxy_for_chat=proxy_for_chat,
            proxy_for_auth=proxy_for_auth,
            image_expire_hours=int(basic_data.get("image_expire_hours", 12)),
            duckmail_base_url=_to_clean_str(basic_data.get("duckmail_base_url"), "https://api.duckmail.sbs"),
            duckmail_api_key=_to_clean_str(basic_data.get("duckmail_api_key")),
            duckmail_verify_ssl=_parse_bool(basic_data.get("duckmail_verify_ssl"), True),
            temp_mail_provider=_normalize_temp_mail_provider(basic_data.get("temp_mail_provider"), "duckmail"),
            moemail_base_url=_to_clean_str(basic_data.get("moemail_base_url"), "https://moemail.nanohajimi.mom"),
            moemail_api_key=_to_clean_str(basic_data.get("moemail_api_key")),
            moemail_domain=_to_clean_str(basic_data.get("moemail_domain")),
            freemail_base_url=_to_clean_str(basic_data.get("freemail_base_url"), "http://your-freemail-server.com"),
            freemail_jwt_token=_to_clean_str(basic_data.get("freemail_jwt_token")),
            freemail_verify_ssl=_parse_bool(basic_data.get("freemail_verify_ssl"), True),
            freemail_domain=_to_clean_str(basic_data.get("freemail_domain")),
            mail_proxy_enabled=_parse_bool(basic_data.get("mail_proxy_enabled"), False),
            gptmail_base_url=_to_clean_str(basic_data.get("gptmail_base_url"), "https://mail.chatgpt.org.uk"),
            gptmail_api_key=_to_clean_str(basic_data.get("gptmail_api_key")),
            gptmail_verify_ssl=_parse_bool(basic_data.get("gptmail_verify_ssl"), True),
            gptmail_domain=_to_clean_str(basic_data.get("gptmail_domain")),
            cfmail_base_url=_to_clean_str(basic_data.get("cfmail_base_url")),
            cfmail_api_key=_to_clean_str(basic_data.get("cfmail_api_key")),
            cfmail_verify_ssl=_parse_bool(basic_data.get("cfmail_verify_ssl"), True),
            cfmail_domain=_to_clean_str(basic_data.get("cfmail_domain")),
            browser_mode=browser_mode,
            browser_headless=browser_headless,
            refresh_window_hours=int(basic_data.get("refresh_window_hours", 1)),
            register_domain=_to_clean_str(basic_data.get("register_domain")),
            register_default_count=max(1, int(basic_data.get("register_default_count", 20))),
        )

    def _build_retry_config(self, retry_data: dict[str, object]) -> RetryConfig:
        return RetryConfig(**retry_data)

    def _build_runtime_basic_data(self, data: dict[str, object]) -> dict[str, object]:
        basic_data = _as_dict(data.get("basic"))
        refresh_data = _as_dict(data.get("refresh_settings"))

        duckmail = _as_dict(refresh_data.get("duckmail"))
        moemail = _as_dict(refresh_data.get("moemail"))
        freemail = _as_dict(refresh_data.get("freemail"))
        gptmail = _as_dict(refresh_data.get("gptmail"))
        cfmail = _as_dict(refresh_data.get("cfmail"))

        basic_data.update(
            {
                "proxy_for_auth": _pick_defined(
                    refresh_data.get("proxy_for_auth"),
                    basic_data.get("proxy_for_auth"),
                    "",
                ),
                "duckmail_base_url": _pick_defined(
                    duckmail.get("base_url"),
                    basic_data.get("duckmail_base_url"),
                    "https://api.duckmail.sbs",
                ),
                "duckmail_api_key": _pick_defined(
                    duckmail.get("api_key"),
                    basic_data.get("duckmail_api_key"),
                    "",
                ),
                "duckmail_verify_ssl": _pick_defined(
                    duckmail.get("verify_ssl"),
                    basic_data.get("duckmail_verify_ssl"),
                    True,
                ),
                "temp_mail_provider": _pick_defined(
                    refresh_data.get("temp_mail_provider"),
                    basic_data.get("temp_mail_provider"),
                    "duckmail",
                ),
                "moemail_base_url": _pick_defined(
                    moemail.get("base_url"),
                    basic_data.get("moemail_base_url"),
                    "https://moemail.nanohajimi.mom",
                ),
                "moemail_api_key": _pick_defined(
                    moemail.get("api_key"),
                    basic_data.get("moemail_api_key"),
                    "",
                ),
                "moemail_domain": _pick_defined(
                    moemail.get("domain"),
                    basic_data.get("moemail_domain"),
                    "",
                ),
                "freemail_base_url": _pick_defined(
                    freemail.get("base_url"),
                    basic_data.get("freemail_base_url"),
                    "http://your-freemail-server.com",
                ),
                "freemail_jwt_token": _pick_defined(
                    freemail.get("jwt_token"),
                    basic_data.get("freemail_jwt_token"),
                    "",
                ),
                "freemail_verify_ssl": _pick_defined(
                    freemail.get("verify_ssl"),
                    basic_data.get("freemail_verify_ssl"),
                    True,
                ),
                "freemail_domain": _pick_defined(
                    freemail.get("domain"),
                    basic_data.get("freemail_domain"),
                    "",
                ),
                "mail_proxy_enabled": _pick_defined(
                    refresh_data.get("mail_proxy_enabled"),
                    basic_data.get("mail_proxy_enabled"),
                    False,
                ),
                "gptmail_base_url": _pick_defined(
                    gptmail.get("base_url"),
                    basic_data.get("gptmail_base_url"),
                    "https://mail.chatgpt.org.uk",
                ),
                "gptmail_api_key": _pick_defined(
                    gptmail.get("api_key"),
                    basic_data.get("gptmail_api_key"),
                    "",
                ),
                "gptmail_verify_ssl": _pick_defined(
                    gptmail.get("verify_ssl"),
                    basic_data.get("gptmail_verify_ssl"),
                    True,
                ),
                "gptmail_domain": _pick_defined(
                    gptmail.get("domain"),
                    basic_data.get("gptmail_domain"),
                    "",
                ),
                "cfmail_base_url": _pick_defined(
                    cfmail.get("base_url"),
                    basic_data.get("cfmail_base_url"),
                    "",
                ),
                "cfmail_api_key": _pick_defined(
                    cfmail.get("api_key"),
                    basic_data.get("cfmail_api_key"),
                    "",
                ),
                "cfmail_verify_ssl": _pick_defined(
                    cfmail.get("verify_ssl"),
                    basic_data.get("cfmail_verify_ssl"),
                    True,
                ),
                "cfmail_domain": _pick_defined(
                    cfmail.get("domain"),
                    basic_data.get("cfmail_domain"),
                    "",
                ),
                "browser_mode": _pick_defined(
                    refresh_data.get("browser_mode"),
                    basic_data.get("browser_mode"),
                    None,
                ),
                "browser_headless": _pick_defined(
                    refresh_data.get("browser_headless"),
                    basic_data.get("browser_headless"),
                    False,
                ),
                "refresh_window_hours": _pick_defined(
                    refresh_data.get("refresh_window_hours"),
                    basic_data.get("refresh_window_hours"),
                    1,
                ),
                "register_domain": _pick_defined(
                    refresh_data.get("register_domain"),
                    basic_data.get("register_domain"),
                    "",
                ),
                "register_default_count": _pick_defined(
                    refresh_data.get("register_default_count"),
                    basic_data.get("register_default_count"),
                    20,
                ),
            }
        )
        return basic_data

    def _build_runtime_retry_data(self, data: dict[str, object]) -> dict[str, object]:
        retry_data = _as_dict(data.get("retry"))
        refresh_data = _as_dict(data.get("refresh_settings"))

        retry_data.update(
            {
                "auto_refresh_accounts_seconds": _pick_defined(
                    refresh_data.get("auto_refresh_accounts_seconds"),
                    retry_data.get("auto_refresh_accounts_seconds"),
                    60,
                ),
                "scheduled_refresh_enabled": _pick_defined(
                    refresh_data.get("scheduled_refresh_enabled"),
                    retry_data.get("scheduled_refresh_enabled"),
                    False,
                ),
                "scheduled_refresh_interval_minutes": _pick_defined(
                    refresh_data.get("scheduled_refresh_interval_minutes"),
                    retry_data.get("scheduled_refresh_interval_minutes"),
                    30,
                ),
                "scheduled_refresh_cron": _pick_defined(
                    refresh_data.get("scheduled_refresh_cron"),
                    retry_data.get("scheduled_refresh_cron"),
                    "",
                ),
                "verification_code_resend_count": _pick_defined(
                    refresh_data.get("verification_code_resend_count"),
                    retry_data.get("verification_code_resend_count"),
                    2,
                ),
                "refresh_batch_size": _pick_defined(
                    refresh_data.get("refresh_batch_size"),
                    retry_data.get("refresh_batch_size"),
                    5,
                ),
                "refresh_batch_interval_minutes": _pick_defined(
                    refresh_data.get("refresh_batch_interval_minutes"),
                    retry_data.get("refresh_batch_interval_minutes"),
                    30,
                ),
                "refresh_cooldown_hours": _pick_defined(
                    refresh_data.get("refresh_cooldown_hours"),
                    retry_data.get("refresh_cooldown_hours"),
                    12.0,
                ),
                "delete_expired_accounts": _pick_defined(
                    refresh_data.get("delete_expired_accounts"),
                    retry_data.get("delete_expired_accounts"),
                    False,
                ),
                "auto_register_enabled": _pick_defined(
                    refresh_data.get("auto_register_enabled"),
                    retry_data.get("auto_register_enabled"),
                    False,
                ),
                "min_account_count": _pick_defined(
                    refresh_data.get("min_account_count"),
                    retry_data.get("min_account_count"),
                    0,
                ),
            }
        )
        return retry_data

    def _build_refresh_settings_snapshot(
        self,
        basic_config: BasicConfig,
        retry_config: RetryConfig,
    ) -> dict[str, object]:
        browser_mode, browser_headless = _normalize_browser_mode(
            basic_config.browser_mode,
            basic_config.browser_headless,
        )
        return {
            "proxy_for_auth": basic_config.proxy_for_auth,
            "duckmail": {
                "base_url": basic_config.duckmail_base_url,
                "api_key": basic_config.duckmail_api_key,
                "verify_ssl": basic_config.duckmail_verify_ssl,
            },
            "temp_mail_provider": basic_config.temp_mail_provider,
            "moemail": {
                "base_url": basic_config.moemail_base_url,
                "api_key": basic_config.moemail_api_key,
                "domain": basic_config.moemail_domain,
            },
            "freemail": {
                "base_url": basic_config.freemail_base_url,
                "jwt_token": basic_config.freemail_jwt_token,
                "verify_ssl": basic_config.freemail_verify_ssl,
                "domain": basic_config.freemail_domain,
            },
            "mail_proxy_enabled": basic_config.mail_proxy_enabled,
            "gptmail": {
                "base_url": basic_config.gptmail_base_url,
                "api_key": basic_config.gptmail_api_key,
                "verify_ssl": basic_config.gptmail_verify_ssl,
                "domain": basic_config.gptmail_domain,
            },
            "cfmail": {
                "base_url": basic_config.cfmail_base_url,
                "api_key": basic_config.cfmail_api_key,
                "verify_ssl": basic_config.cfmail_verify_ssl,
                "domain": basic_config.cfmail_domain,
            },
            "browser_mode": browser_mode,
            "browser_headless": browser_headless,
            "refresh_window_hours": basic_config.refresh_window_hours,
            "register_domain": basic_config.register_domain,
            "register_default_count": basic_config.register_default_count,
            "auto_refresh_accounts_seconds": retry_config.auto_refresh_accounts_seconds,
            "scheduled_refresh_enabled": retry_config.scheduled_refresh_enabled,
            "scheduled_refresh_interval_minutes": retry_config.scheduled_refresh_interval_minutes,
            "scheduled_refresh_cron": retry_config.scheduled_refresh_cron,
            "verification_code_resend_count": retry_config.verification_code_resend_count,
            "refresh_batch_size": retry_config.refresh_batch_size,
            "refresh_batch_interval_minutes": retry_config.refresh_batch_interval_minutes,
            "refresh_cooldown_hours": retry_config.refresh_cooldown_hours,
            "delete_expired_accounts": retry_config.delete_expired_accounts,
            "auto_register_enabled": retry_config.auto_register_enabled,
            "min_account_count": retry_config.min_account_count,
        }

    def _build_storage_snapshot(
        self,
        *,
        basic_config: BasicConfig,
        image_generation_config: ImageGenerationConfig,
        video_generation_config: VideoGenerationConfig,
        retry_config: RetryConfig,
        quota_limits_config: QuotaLimitsConfig,
        public_display_config: PublicDisplayConfig,
        session_config: SessionConfig,
    ) -> dict[str, object]:
        return {
            "basic": {
                field: getattr(basic_config, field)
                for field in STORAGE_BASIC_FIELDS
            },
            "image_generation": _model_dump(image_generation_config),
            "video_generation": _model_dump(video_generation_config),
            "retry": {
                field: getattr(retry_config, field)
                for field in STORAGE_RETRY_FIELDS
            },
            "quota_limits": _model_dump(quota_limits_config),
            "public_display": _model_dump(public_display_config),
            "session": _model_dump(session_config),
            "refresh_settings": self._build_refresh_settings_snapshot(basic_config, retry_config),
        }

    def _load_yaml(self) -> dict:
        if storage.is_database_enabled():
            try:
                data = storage.load_settings_sync()
                if data is None:
                    print("[WARN] settings not found, booting with defaults")
                    return {}
                if isinstance(data, dict):
                    return data
                return {}
            except RuntimeError:
                raise
            except Exception as exc:
                print(f"[ERROR] storage load failed: {exc}")
                raise RuntimeError(f"storage load failed: {exc}") from exc

        print("[ERROR] DATABASE_URL is not configured")
        raise RuntimeError("DATABASE_URL is not configured")

    def _generate_secret(self) -> str:
        return secrets.token_urlsafe(32)

    def save_settings_snapshot(self, data: dict) -> None:
        if not storage.is_database_enabled():
            raise RuntimeError("Database is not enabled")

        try:
            security_config = SecurityConfig(
                admin_key=os.getenv("ADMIN_KEY", ""),
                session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret()),
            )
            basic_config = self._build_basic_config(self._build_runtime_basic_data(data))
            image_generation_config = ImageGenerationConfig(**dict(data.get("image_generation", {}) or {}))
            video_generation_config = VideoGenerationConfig(**dict(data.get("video_generation", {}) or {}))
            retry_config = self._build_retry_config(self._build_runtime_retry_data(data))
            quota_limits_config = QuotaLimitsConfig(**dict(data.get("quota_limits", {}) or {}))
            public_display_config = PublicDisplayConfig(**dict(data.get("public_display", {}) or {}))
            session_config = SessionConfig(**dict(data.get("session", {}) or {}))

            AppConfig(
                security=security_config,
                basic=basic_config,
                image_generation=image_generation_config,
                video_generation=video_generation_config,
                retry=retry_config,
                quota_limits=quota_limits_config,
                public_display=public_display_config,
                session=session_config,
            )
            normalized_snapshot = self._build_storage_snapshot(
                basic_config=basic_config,
                image_generation_config=image_generation_config,
                video_generation_config=video_generation_config,
                retry_config=retry_config,
                quota_limits_config=quota_limits_config,
                public_display_config=public_display_config,
                session_config=session_config,
            )
        except Exception as exc:
            raise ValueError(f"config validation failed: {exc}") from exc

        try:
            saved = storage.save_settings_sync(normalized_snapshot)
            if saved:
                return
        except Exception as exc:
            print(f"[WARN] storage save failed: {exc}")
        raise RuntimeError("Database write failed")

    def save_yaml(self, data: dict) -> None:
        self.save_settings_snapshot(data)

    def reload(self) -> None:
        self.load()

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def api_key(self) -> str:
        return self._config.basic.api_key

    @property
    def admin_key(self) -> str:
        return self._config.security.admin_key

    @property
    def session_secret_key(self) -> str:
        return self._config.security.session_secret_key

    @property
    def proxy_for_chat(self) -> str:
        return self._config.basic.proxy_for_chat

    @property
    def base_url(self) -> str:
        return self._config.basic.base_url

    @property
    def logo_url(self) -> str:
        return self._config.public_display.logo_url

    @property
    def chat_url(self) -> str:
        return self._config.public_display.chat_url

    @property
    def image_generation_enabled(self) -> bool:
        return self._config.image_generation.enabled

    @property
    def image_generation_models(self) -> List[str]:
        return self._config.image_generation.supported_models

    @property
    def image_output_format(self) -> str:
        return self._config.image_generation.output_format

    @property
    def video_output_format(self) -> str:
        return self._config.video_generation.output_format

    @property
    def session_expire_hours(self) -> int:
        return self._config.session.expire_hours

    @property
    def max_account_switch_tries(self) -> int:
        return self._config.retry.max_account_switch_tries

    @property
    def rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.text_rate_limit_cooldown_seconds

    @property
    def text_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.text_rate_limit_cooldown_seconds

    @property
    def images_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.images_rate_limit_cooldown_seconds

    @property
    def videos_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.videos_rate_limit_cooldown_seconds

    @property
    def session_cache_ttl_seconds(self) -> int:
        return self._config.retry.session_cache_ttl_seconds


config_manager = ConfigManager()


def get_config() -> AppConfig:
    return config_manager.config


class _ConfigProxy:
    @property
    def basic(self):
        return config_manager.config.basic

    @property
    def security(self):
        return config_manager.config.security

    @property
    def image_generation(self):
        return config_manager.config.image_generation

    @property
    def video_generation(self):
        return config_manager.config.video_generation

    @property
    def retry(self):
        return config_manager.config.retry

    @property
    def quota_limits(self):
        return config_manager.config.quota_limits

    @property
    def public_display(self):
        return config_manager.config.public_display

    @property
    def session(self):
        return config_manager.config.session


config = _ConfigProxy()
