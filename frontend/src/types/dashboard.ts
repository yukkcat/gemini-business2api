export type DashboardTimeRange = '24h' | '7d' | '30d'

export const DASHBOARD_TIME_RANGE_VALUES = ['24h', '7d', '30d'] as const satisfies readonly DashboardTimeRange[]

export const DASHBOARD_TIME_RANGE_OPTIONS = [
  { label: '24小时', value: '24h' },
  { label: '7天', value: '7d' },
  { label: '30天', value: '30d' },
] as const satisfies ReadonlyArray<{ label: string; value: DashboardTimeRange }>

export const normalizeDashboardTimeRange = (
  value: unknown,
  fallback: DashboardTimeRange = '24h',
): DashboardTimeRange => {
  const normalized = String(value || '').trim() as DashboardTimeRange
  return DASHBOARD_TIME_RANGE_VALUES.includes(normalized) ? normalized : fallback
}

export interface AdminStatsTrend {
  labels: string[]
  total_requests: number[]
  failed_requests: number[]
  rate_limited_requests: number[]
  model_requests: Record<string, number[]>
  model_ttfb_times: Record<string, number[]>
  model_total_times: Record<string, number[]>
}

export interface AdminStats {
  total_accounts: number
  active_accounts: number
  failed_accounts: number
  rate_limited_accounts: number
  idle_accounts: number
  success_count: number
  failed_count: number
  trend: AdminStatsTrend
}
