// API 类型定义

export interface QuotaStatus {
  available: boolean
  remaining_seconds?: number
  reason?: string  // 受限原因（如"对话配额受限"）
  daily_used?: number
  daily_limit?: number
}

export interface AccountQuotaStatus {
  quotas: {
    text: QuotaStatus
    images: QuotaStatus
    videos: QuotaStatus
  }
  limited_count: number
  total_count: number
  is_expired: boolean
}

export type AccountStateCode =
  | 'active'
  | 'manual_disabled'
  | 'access_restricted'
  | 'expired'
  | 'expiring_soon'
  | 'rate_limited'
  | 'quota_limited'
  | 'unavailable'
  | 'unknown'

export type AccountStateSeverity = 'success' | 'warning' | 'danger' | 'muted'

export interface AccountState {
  code: AccountStateCode
  label: string
  severity: AccountStateSeverity
  reason: string | null
  cooldown_seconds: number
  can_enable: boolean
  can_disable: boolean
  can_delete: boolean
}

export interface AdminAccount {
  id: string
  state?: AccountState
  status: string
  expires_at: string
  remaining_hours: number | null
  remaining_display: string
  is_available: boolean
  error_count: number
  failure_count: number
  disabled: boolean
  disabled_reason: string | null
  cooldown_seconds: number
  cooldown_reason: string | null
  conversation_count: number
  quota_status: AccountQuotaStatus
  trial_end?: string | null
  trial_days_remaining?: number | null
}

export type AccountListStatus = 'all' | AccountStateCode

export interface AccountsListParams {
  page?: number
  pageSize?: number
  query?: string
  status?: AccountListStatus
}

export interface AccountsListResponse {
  total: number
  page: number
  page_size: number
  total_pages: number
  query: string
  status: AccountListStatus
  accounts: AdminAccount[]
}

export interface AccountConfigItem {
  id: string
  secure_c_ses: string
  csesidx: string
  config_id: string
  host_c_oses?: string
  expires_at?: string
  mail_provider?: string
  mail_address?: string
  mail_password?: string
  mail_client_id?: string
  mail_refresh_token?: string
  mail_tenant?: string
  mail_base_url?: string
  mail_api_key?: string
  mail_jwt_token?: string
  mail_verify_ssl?: boolean
  mail_domain?: string
  disabled?: boolean
  disabled_reason?: string | null
  trial_end?: string | null
  [key: string]: unknown
}

export interface AccountsConfigResponse {
  accounts: AccountConfigItem[]
}

export interface Stats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  expired_accounts: number
  total_requests: number
  total_visitors: number
  requests_per_hour: number
}

export interface RefreshSettings {
  proxy_for_auth?: string
  duckmail: {
    base_url?: string
    api_key?: string
    verify_ssl?: boolean
  }
  temp_mail_provider?: 'duckmail' | 'moemail' | 'freemail' | 'gptmail' | 'cfmail'
  moemail: {
    base_url?: string
    api_key?: string
    domain?: string
  }
  freemail: {
    base_url?: string
    jwt_token?: string
    verify_ssl?: boolean
    domain?: string
  }
  mail_proxy_enabled?: boolean
  gptmail: {
    base_url?: string
    api_key?: string
    verify_ssl?: boolean
    domain?: string
  }
  cfmail: {
    base_url?: string
    api_key?: string
    verify_ssl?: boolean
    domain?: string
  }
  browser_mode?: 'normal' | 'silent' | 'headless'
  browser_headless?: boolean
  refresh_window_hours?: number
  register_domain?: string
  register_default_count?: number
  auto_refresh_accounts_seconds?: number
  scheduled_refresh_enabled?: boolean
  scheduled_refresh_interval_minutes?: number
  scheduled_refresh_cron?: string
  verification_code_resend_count?: number
  refresh_batch_size?: number
  refresh_batch_interval_minutes?: number
  refresh_cooldown_hours?: number
  delete_expired_accounts?: boolean
  auto_register_enabled?: boolean
  min_account_count?: number
}

export interface Settings {
  basic: {
    api_key?: string
    base_url?: string
    proxy_for_chat?: string
    image_expire_hours?: number
  }
  retry: {
    max_account_switch_tries: number
    rate_limit_cooldown_seconds?: number
    text_rate_limit_cooldown_seconds: number
    images_rate_limit_cooldown_seconds: number
    videos_rate_limit_cooldown_seconds: number
    session_cache_ttl_seconds: number
  }
  public_display: {
    logo_url?: string
    chat_url?: string
  }
  image_generation: {
    enabled: boolean
    supported_models: string[]
    output_format?: 'base64' | 'url'
  }
  video_generation: {
    output_format?: 'html' | 'url' | 'markdown'
  }
  session: {
    expire_hours: number
  }
  refresh_settings: RefreshSettings
  quota_limits: {
    enabled: boolean
    text_daily_limit: number
    images_daily_limit: number
    videos_daily_limit: number
  }
}

export interface LogEntry {
  time: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'DEBUG'
  message: string
  row_id?: string
  tags?: string[]
  account_id?: string
  text?: string
  req_id?: string
  layer?: string
  lane?: string
  model?: string
  kind?: string
  stage?: string
  served_label?: string
}

export interface AdminLogGroup {
  id?: string
  request_id?: string
  status?: string
  account_id?: string
  model?: string
  lane?: string
  terminal_kind?: string
  started_at?: string
  ended_at?: string
  user_preview?: string
  assistant_preview?: string
  row_ids?: string[]
  events?: Array<{
    time?: string
    type?: string
    status?: string
    content?: string
  }>
}

export interface LogsResponse {
  total: number
  limit: number
  logs: LogEntry[]
}

export interface AdminLogStats {
  memory: {
    total: number
    by_level: Record<string, number>
    capacity: number
  }
  errors: {
    count: number
    recent: LogEntry[]
  }
  chat_count: number
}

export interface AdminLogsResponse extends LogsResponse {
  filters?: {
    level?: string | null
    search?: string | null
    start_time?: string | null
    end_time?: string | null
  }
  stats: AdminLogStats
  groups?: AdminLogGroup[]
}

export type PublicLogStatus = 'success' | 'error' | 'timeout' | 'in_progress'

export interface PublicLogEvent {
  time: string
  type: 'start' | 'select' | 'retry' | 'switch' | 'complete'
  status?: 'success' | 'error' | 'timeout'
  content: string
}

export interface PublicLogGroup {
  request_id: string
  start_time: string
  status: PublicLogStatus
  events: PublicLogEvent[]
}

export interface PublicLogsResponse {
  total: number
  logs: PublicLogGroup[]
  error?: string
}

export interface AdminStatsTrend {
  labels: string[]
  total_requests: number[]
  failed_requests: number[]
  rate_limited_requests: number[]
  model_requests?: Record<string, number[]>
  model_ttfb_times?: Record<string, number[]>
  model_total_times?: Record<string, number[]>
}

export interface AdminStats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  idle_accounts: number
  success_count?: number
  failed_count?: number
  trend: AdminStatsTrend
}

export interface PublicStats {
  total_visitors: number
  total_requests: number
  requests_per_minute: number
  load_status: 'low' | 'medium' | 'high'
  load_color: string
}

export interface PublicDisplay {
  logo_url?: string
  chat_url?: string
}

export interface UptimeHeartbeat {
  time: string
  success: boolean
  latency_ms?: number | null
  status_code?: number | null
  level?: 'up' | 'down' | 'warn'
}

export interface UptimeService {
  name: string
  status: 'up' | 'down' | 'warn' | 'unknown'
  uptime: number
  total: number
  success: number
  heartbeats: UptimeHeartbeat[]
}

export interface UptimeResponse {
  services: Record<string, UptimeService>
  updated_at: string
}

export interface LoginRequest {
  password: string
}

export interface LoginResponse {
  success: boolean
  message?: string
}

export interface VersionInfoResponse {
  version: string
  tag: string
  commit: string
}

export interface VersionCheckResponse extends VersionInfoResponse {
  repository: string
  latest_tag: string
  latest_version: string
  release_url: string
  is_latest: boolean
  update_available: boolean
  check_error?: string
}
