import type { RefreshSettings, Settings } from '@/types/api'

export const DEFAULT_BASIC_SETTINGS: Settings['basic'] = {
  api_key: '',
  base_url: '',
  proxy_for_chat: '',
  image_expire_hours: 12,
}

export const DEFAULT_RETRY_SETTINGS: Settings['retry'] = {
  max_account_switch_tries: 5,
  rate_limit_cooldown_seconds: 7200,
  text_rate_limit_cooldown_seconds: 7200,
  images_rate_limit_cooldown_seconds: 14400,
  videos_rate_limit_cooldown_seconds: 14400,
  session_cache_ttl_seconds: 3600,
}

export const DEFAULT_IMAGE_GENERATION_SETTINGS: Settings['image_generation'] = {
  enabled: false,
  supported_models: [],
  output_format: 'base64',
}

export const DEFAULT_VIDEO_GENERATION_SETTINGS: Settings['video_generation'] = {
  output_format: 'html',
}

export const DEFAULT_QUOTA_LIMITS_SETTINGS: Settings['quota_limits'] = {
  enabled: true,
  text_daily_limit: 120,
  images_daily_limit: 2,
  videos_daily_limit: 1,
}

export const DEFAULT_PUBLIC_DISPLAY_SETTINGS: Settings['public_display'] = {
  logo_url: '',
  chat_url: '',
}

export const DEFAULT_SESSION_SETTINGS: Settings['session'] = {
  expire_hours: 24,
}

export const createDefaultRefreshSettings = (): RefreshSettings => ({
  proxy_for_auth: '',
  duckmail: {
    base_url: 'https://api.duckmail.sbs',
    api_key: '',
    verify_ssl: true,
  },
  temp_mail_provider: 'duckmail',
  moemail: {
    base_url: 'https://moemail.nanohajimi.mom',
    api_key: '',
    domain: '',
  },
  freemail: {
    base_url: 'http://your-freemail-server.com',
    jwt_token: '',
    verify_ssl: true,
    domain: '',
  },
  mail_proxy_enabled: false,
  gptmail: {
    base_url: 'https://mail.chatgpt.org.uk',
    api_key: '',
    verify_ssl: true,
    domain: '',
  },
  cfmail: {
    base_url: '',
    api_key: '',
    verify_ssl: true,
    domain: '',
  },
  browser_mode: 'normal',
  browser_headless: false,
  refresh_window_hours: 1,
  register_domain: '',
  register_default_count: 20,
  auto_refresh_accounts_seconds: 60,
  scheduled_refresh_enabled: false,
  scheduled_refresh_interval_minutes: 30,
  scheduled_refresh_cron: '',
  verification_code_resend_count: 2,
  refresh_batch_size: 5,
  refresh_batch_interval_minutes: 30,
  refresh_cooldown_hours: 12,
  delete_expired_accounts: false,
  auto_register_enabled: false,
  min_account_count: 0,
})

export const createDefaultSettings = (): Settings => ({
  basic: { ...DEFAULT_BASIC_SETTINGS },
  retry: { ...DEFAULT_RETRY_SETTINGS },
  public_display: { ...DEFAULT_PUBLIC_DISPLAY_SETTINGS },
  image_generation: {
    ...DEFAULT_IMAGE_GENERATION_SETTINGS,
    supported_models: [...DEFAULT_IMAGE_GENERATION_SETTINGS.supported_models],
  },
  video_generation: { ...DEFAULT_VIDEO_GENERATION_SETTINGS },
  session: { ...DEFAULT_SESSION_SETTINGS },
  refresh_settings: createDefaultRefreshSettings(),
  quota_limits: { ...DEFAULT_QUOTA_LIMITS_SETTINGS },
})
