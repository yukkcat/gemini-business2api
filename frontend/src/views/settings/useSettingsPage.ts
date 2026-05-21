import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'
import type { Settings } from '@/types/settings'
import {
  DEFAULT_COOLDOWN_HOURS,
  browserModeOptions,
  imageOutputOptions,
  tempMailProviderOptions,
  videoOutputOptions,
} from './settingsOptions'
import { SETTINGS_LIMITS } from './settingsConstraints'
import { clampDecimal, clampInteger, toCooldownHours } from './settingsHelpers'
import { normalizeSettings } from './settingsNormalize'
import { syncRefreshMirrors } from './settingsRefresh'

export function useSettingsPage() {
  const settingsStore = useSettingsStore()
  const { settings, isLoading } = storeToRefs(settingsStore)
  const toast = useToast()

  const localSettings = ref<Settings | null>(null)
  const isSaving = ref(false)
  const errorMessage = ref('')

  const createNumberInputBinding = (
    getter: () => number | undefined,
    setter: (value: number) => void,
    normalize: (value: number) => number = (value) => value,
  ) => computed({
    get: () => {
      const value = getter()
      return Number.isFinite(value) ? String(value) : ''
    },
    set: (raw: string | number) => {
      const parsed = typeof raw === 'number' ? raw : Number(String(raw).trim())
      if (Number.isFinite(parsed)) {
        setter(normalize(parsed))
      }
    },
  })

  const createCooldownHoursBinding = (
    key: 'text_rate_limit_cooldown_seconds' | 'images_rate_limit_cooldown_seconds' | 'videos_rate_limit_cooldown_seconds',
    fallbackHours: number,
    maxHours = SETTINGS_LIMITS.retry.textCooldownSeconds.max / 3600,
  ) => createNumberInputBinding(
    () => toCooldownHours(localSettings.value?.retry?.[key], fallbackHours),
    (value) => {
      if (localSettings.value?.retry) {
        localSettings.value.retry[key] = value * 3600
      }
    },
    (value) => clampInteger(value, 1, maxHours),
  )

  const createRefreshNumberBinding = (
    getter: () => number | undefined,
    setter: (value: number) => void,
    min: number,
    max: number,
  ) => createNumberInputBinding(getter, setter, (value) => clampInteger(value, min, max))

  const maxAccountSwitchTriesInput = createNumberInputBinding(
    () => localSettings.value?.retry?.max_account_switch_tries,
    (value) => {
      if (localSettings.value?.retry) {
        localSettings.value.retry.max_account_switch_tries = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.retry.maxAccountSwitchTries.min,
      SETTINGS_LIMITS.retry.maxAccountSwitchTries.max,
    ),
  )

  const textCooldownHoursInput = createCooldownHoursBinding(
    'text_rate_limit_cooldown_seconds',
    DEFAULT_COOLDOWN_HOURS.text,
  )

  const imagesCooldownHoursInput = createCooldownHoursBinding(
    'images_rate_limit_cooldown_seconds',
    DEFAULT_COOLDOWN_HOURS.images,
  )

  const videosCooldownHoursInput = createCooldownHoursBinding(
    'videos_rate_limit_cooldown_seconds',
    DEFAULT_COOLDOWN_HOURS.videos,
  )

  const sessionCacheTtlInput = createNumberInputBinding(
    () => localSettings.value?.retry?.session_cache_ttl_seconds,
    (value) => {
      if (localSettings.value?.retry) {
        localSettings.value.retry.session_cache_ttl_seconds = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.retry.sessionCacheTtlSeconds.min,
      SETTINGS_LIMITS.retry.sessionCacheTtlSeconds.max,
    ),
  )

  const registerDefaultCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.register_default_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.register_default_count = value
      }
    },
    SETTINGS_LIMITS.refresh.registerDefaultCount.min,
    SETTINGS_LIMITS.refresh.registerDefaultCount.max,
  )

  const refreshWindowHoursInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_window_hours,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_window_hours = value
      }
    },
    SETTINGS_LIMITS.refresh.refreshWindowHours.min,
    SETTINGS_LIMITS.refresh.refreshWindowHours.max,
  )

  const autoRefreshAccountsSecondsInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.auto_refresh_accounts_seconds,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.auto_refresh_accounts_seconds = value
      }
    },
    SETTINGS_LIMITS.refresh.autoRefreshAccountsSeconds.min,
    SETTINGS_LIMITS.refresh.autoRefreshAccountsSeconds.max,
  )

  const scheduledRefreshIntervalMinutesInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.scheduled_refresh_interval_minutes,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.scheduled_refresh_interval_minutes = value
      }
    },
    SETTINGS_LIMITS.refresh.scheduledRefreshIntervalMinutes.min,
    SETTINGS_LIMITS.refresh.scheduledRefreshIntervalMinutes.max,
  )

  const verificationCodeResendCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.verification_code_resend_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.verification_code_resend_count = value
      }
    },
    SETTINGS_LIMITS.refresh.verificationCodeResendCount.min,
    SETTINGS_LIMITS.refresh.verificationCodeResendCount.max,
  )

  const refreshBatchSizeInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_batch_size,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_batch_size = value
      }
    },
    SETTINGS_LIMITS.refresh.refreshBatchSize.min,
    SETTINGS_LIMITS.refresh.refreshBatchSize.max,
  )

  const refreshBatchIntervalMinutesInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_batch_interval_minutes,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_batch_interval_minutes = value
      }
    },
    SETTINGS_LIMITS.refresh.refreshBatchIntervalMinutes.min,
    SETTINGS_LIMITS.refresh.refreshBatchIntervalMinutes.max,
  )

  const refreshCooldownHoursInput = createNumberInputBinding(
    () => localSettings.value?.refresh_settings?.refresh_cooldown_hours,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_cooldown_hours = value
      }
    },
    (value) => clampDecimal(
      value,
      SETTINGS_LIMITS.refresh.refreshCooldownHours.min,
      SETTINGS_LIMITS.refresh.refreshCooldownHours.max,
    ),
  )

  const minAccountCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.min_account_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.min_account_count = value
      }
    },
    SETTINGS_LIMITS.refresh.minAccountCount.min,
    SETTINGS_LIMITS.refresh.minAccountCount.max,
  )

  const quotaTextDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.text_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.text_daily_limit = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.quota.dailyLimit.min,
      SETTINGS_LIMITS.quota.dailyLimit.max,
    ),
  )

  const quotaImagesDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.images_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.images_daily_limit = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.quota.dailyLimit.min,
      SETTINGS_LIMITS.quota.dailyLimit.max,
    ),
  )

  const quotaVideosDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.videos_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.videos_daily_limit = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.quota.dailyLimit.min,
      SETTINGS_LIMITS.quota.dailyLimit.max,
    ),
  )

  const sessionExpireHoursInput = createNumberInputBinding(
    () => localSettings.value?.session?.expire_hours,
    (value) => {
      if (localSettings.value?.session) {
        localSettings.value.session.expire_hours = value
      }
    },
    (value) => clampInteger(
      value,
      SETTINGS_LIMITS.session.expireHours.min,
      SETTINGS_LIMITS.session.expireHours.max,
    ),
  )

  const imageModelOptions = computed(() => {
    const options = [
      { label: 'Gemini 3.1 Pro Preview', value: 'gemini-3.1-pro-preview' },
      { label: 'Gemini 3.1 Flash', value: 'gemini-3.1-flash' },
      { label: 'Gemini 2.5 Pro', value: 'gemini-2.5-pro' },
      { label: 'Gemini Auto', value: 'gemini-auto' },
    ]

    const selected = localSettings.value?.image_generation.supported_models || []
    for (const value of selected) {
      if (!options.some((option) => option.value === value)) {
        options.push({ label: value, value })
      }
    }

    return options
  })

  watch(settings, (value) => {
    if (!value) return
    localSettings.value = normalizeSettings(value)
  }, { immediate: true })

  onMounted(async () => {
    if (!settings.value) {
      await settingsStore.loadSettings()
    }
  })

  const handleSave = async () => {
    if (!localSettings.value) return

    errorMessage.value = ''
    isSaving.value = true

    try {
      const payload = normalizeSettings(JSON.parse(JSON.stringify(localSettings.value)) as Settings)
      syncRefreshMirrors(payload)
      await settingsStore.updateSettings(payload)
      toast.success('设置保存成功')
    } catch (error: any) {
      errorMessage.value = error.message || '保存失败'
      toast.error(error.message || '保存失败')
    } finally {
      isSaving.value = false
    }
  }

  return {
    browserModeOptions,
    tempMailProviderOptions,
    imageOutputOptions,
    videoOutputOptions,
    imageModelOptions,
    isLoading,
    localSettings,
    isSaving,
    errorMessage,
    maxAccountSwitchTriesInput,
    textCooldownHoursInput,
    imagesCooldownHoursInput,
    videosCooldownHoursInput,
    sessionCacheTtlInput,
    registerDefaultCountInput,
    refreshWindowHoursInput,
    autoRefreshAccountsSecondsInput,
    scheduledRefreshIntervalMinutesInput,
    verificationCodeResendCountInput,
    refreshBatchSizeInput,
    refreshBatchIntervalMinutesInput,
    refreshCooldownHoursInput,
    minAccountCountInput,
    quotaTextDailyLimitInput,
    quotaImagesDailyLimitInput,
    quotaVideosDailyLimitInput,
    sessionExpireHoursInput,
    handleSave,
  }
}
