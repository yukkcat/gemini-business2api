from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


TempMailProvider = Literal["duckmail", "moemail", "freemail", "gptmail", "cfmail"]
BrowserMode = Literal["normal", "silent", "headless"]
ImageOutputFormat = Literal["base64", "url"]
VideoOutputFormat = Literal["html", "url", "markdown"]


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class DuckmailSettingsPayload(StrictModel):
    base_url: str
    api_key: str
    verify_ssl: bool


class MoemailSettingsPayload(StrictModel):
    base_url: str
    api_key: str
    domain: str


class FreemailSettingsPayload(StrictModel):
    base_url: str
    jwt_token: str
    verify_ssl: bool
    domain: str


class GptmailSettingsPayload(StrictModel):
    base_url: str
    api_key: str
    verify_ssl: bool
    domain: str


class CfmailSettingsPayload(StrictModel):
    base_url: str
    api_key: str
    verify_ssl: bool
    domain: str


class BasicSettingsPayload(StrictModel):
    api_key: str
    base_url: str
    proxy_for_chat: str
    image_expire_hours: int = Field(..., ge=-1, le=720)


class RetrySettingsPayload(StrictModel):
    max_account_switch_tries: int = Field(..., ge=1, le=20)
    rate_limit_cooldown_seconds: int = Field(..., ge=3600, le=43200)
    text_rate_limit_cooldown_seconds: int = Field(..., ge=3600, le=86400)
    images_rate_limit_cooldown_seconds: int = Field(..., ge=3600, le=86400)
    videos_rate_limit_cooldown_seconds: int = Field(..., ge=3600, le=86400)
    session_cache_ttl_seconds: int = Field(..., ge=0, le=86400)


class RefreshSettingsPayload(StrictModel):
    proxy_for_auth: str
    duckmail: DuckmailSettingsPayload
    temp_mail_provider: TempMailProvider
    moemail: MoemailSettingsPayload
    freemail: FreemailSettingsPayload
    mail_proxy_enabled: bool
    gptmail: GptmailSettingsPayload
    cfmail: CfmailSettingsPayload
    browser_mode: BrowserMode
    browser_headless: bool
    refresh_window_hours: int = Field(..., ge=0, le=24)
    register_domain: str
    register_default_count: int = Field(..., ge=1, le=200)
    auto_refresh_accounts_seconds: int = Field(..., ge=0, le=86400)
    scheduled_refresh_enabled: bool
    scheduled_refresh_interval_minutes: int = Field(..., ge=0, le=720)
    scheduled_refresh_cron: str
    verification_code_resend_count: int = Field(..., ge=0, le=5)
    refresh_batch_size: int = Field(..., ge=1, le=50)
    refresh_batch_interval_minutes: int = Field(..., ge=0, le=720)
    refresh_cooldown_hours: float = Field(..., ge=0, le=168)
    delete_expired_accounts: bool
    auto_register_enabled: bool
    min_account_count: int = Field(..., ge=0, le=1000)


class ImageGenerationSettingsPayload(StrictModel):
    enabled: bool
    supported_models: List[str] = Field(default_factory=list)
    output_format: ImageOutputFormat


class VideoGenerationSettingsPayload(StrictModel):
    output_format: VideoOutputFormat


class QuotaLimitsSettingsPayload(StrictModel):
    enabled: bool
    text_daily_limit: int = Field(..., ge=0, le=999999)
    images_daily_limit: int = Field(..., ge=0, le=999999)
    videos_daily_limit: int = Field(..., ge=0, le=999999)


class PublicDisplaySettingsPayload(StrictModel):
    logo_url: str
    chat_url: str


class SessionSettingsPayload(StrictModel):
    expire_hours: int = Field(..., ge=1, le=168)


class AdminSettingsPayload(StrictModel):
    basic: BasicSettingsPayload
    retry: RetrySettingsPayload
    public_display: PublicDisplaySettingsPayload
    image_generation: ImageGenerationSettingsPayload
    video_generation: VideoGenerationSettingsPayload
    session: SessionSettingsPayload
    refresh_settings: RefreshSettingsPayload
    quota_limits: QuotaLimitsSettingsPayload


for model in (
    DuckmailSettingsPayload,
    MoemailSettingsPayload,
    FreemailSettingsPayload,
    GptmailSettingsPayload,
    CfmailSettingsPayload,
    BasicSettingsPayload,
    RetrySettingsPayload,
    RefreshSettingsPayload,
    ImageGenerationSettingsPayload,
    VideoGenerationSettingsPayload,
    QuotaLimitsSettingsPayload,
    PublicDisplaySettingsPayload,
    SessionSettingsPayload,
    AdminSettingsPayload,
):
    model.model_rebuild()
