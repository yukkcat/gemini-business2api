import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'
import type { Settings } from '@/types/api'
import {
  DEFAULT_COOLDOWN_HOURS,
  browserModeOptions,
  imageOutputOptions,
  tempMailProviderOptions,
  videoOutputOptions,
} from './settingsOptions'
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
    maxHours = 24,
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
    (value) => clampInteger(value, 1, 20),
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
    (value) => clampInteger(value, 0, 86400),
  )

  const registerDefaultCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.register_default_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.register_default_count = value
      }
    },
    1,
    200,
  )

  const refreshWindowHoursInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_window_hours,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_window_hours = value
      }
    },
    0,
    24,
  )

  const autoRefreshAccountsSecondsInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.auto_refresh_accounts_seconds,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.auto_refresh_accounts_seconds = value
      }
    },
    0,
    86400,
  )

  const scheduledRefreshIntervalMinutesInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.scheduled_refresh_interval_minutes,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.scheduled_refresh_interval_minutes = value
      }
    },
    0,
    720,
  )

  const verificationCodeResendCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.verification_code_resend_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.verification_code_resend_count = value
      }
    },
    0,
    5,
  )

  const refreshBatchSizeInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_batch_size,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_batch_size = value
      }
    },
    1,
    50,
  )

  const refreshBatchIntervalMinutesInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.refresh_batch_interval_minutes,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_batch_interval_minutes = value
      }
    },
    0,
    720,
  )

  const refreshCooldownHoursInput = createNumberInputBinding(
    () => localSettings.value?.refresh_settings?.refresh_cooldown_hours,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.refresh_cooldown_hours = value
      }
    },
    (value) => clampDecimal(value, 0, 168),
  )

  const minAccountCountInput = createRefreshNumberBinding(
    () => localSettings.value?.refresh_settings?.min_account_count,
    (value) => {
      if (localSettings.value?.refresh_settings) {
        localSettings.value.refresh_settings.min_account_count = value
      }
    },
    0,
    1000,
  )

  const quotaTextDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.text_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.text_daily_limit = value
      }
    },
    (value) => clampInteger(value, 0, 999999),
  )

  const quotaImagesDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.images_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.images_daily_limit = value
      }
    },
    (value) => clampInteger(value, 0, 999999),
  )

  const quotaVideosDailyLimitInput = createNumberInputBinding(
    () => localSettings.value?.quota_limits?.videos_daily_limit,
    (value) => {
      if (localSettings.value?.quota_limits) {
        localSettings.value.quota_limits.videos_daily_limit = value
      }
    },
    (value) => clampInteger(value, 0, 999999),
  )

  const sessionExpireHoursInput = createNumberInputBinding(
    () => localSettings.value?.session?.expire_hours,
    (value) => {
      if (localSettings.value?.session) {
        localSettings.value.session.expire_hours = value
      }
    },
    (value) => clampInteger(value, 1, 168),
  )

  const imageModelOptions = computed(() => {
    const options = [
      { label: 'Gemini 3 Pro Preview', value: 'gemini-3-pro-preview' },
      { label: 'Gemini 3.1 Pro Preview', value: 'gemini-3.1-pro-preview' },
      { label: 'Gemini 3 Flash Preview', value: 'gemini-3-flash-preview' },
      { label: 'Gemini 2.5 Pro', value: 'gemini-2.5-pro' },
      { label: 'Gemini 2.5 Flash', value: 'gemini-2.5-flash' },
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
