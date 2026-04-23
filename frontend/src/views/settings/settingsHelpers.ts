import type { RefreshSettings } from '@/types/api'

export const clampInteger = (
  value: number,
  min: number,
  max: number = Number.MAX_SAFE_INTEGER,
) => Math.max(min, Math.min(max, Math.round(value)))

export const clampDecimal = (value: number, min: number, max: number) =>
  Number(Math.max(min, Math.min(max, value)).toFixed(1))

export const pickString = (fallback: string, ...values: Array<string | undefined>) => {
  for (const value of values) {
    if (typeof value === 'string') return value.trim()
  }
  return fallback
}

export const pickNumber = (fallback: number, ...values: Array<number | undefined>) => {
  for (const value of values) {
    if (Number.isFinite(value)) return Number(value)
  }
  return fallback
}

export const pickBoolean = (fallback: boolean, ...values: Array<boolean | undefined>) => {
  for (const value of values) {
    if (typeof value === 'boolean') return value
  }
  return fallback
}

export const normalizeBrowserMode = (
  mode: string | undefined,
  headless: boolean | undefined,
): RefreshSettings['browser_mode'] => {
  const normalized = mode?.trim().toLowerCase()
  if (normalized === 'normal' || normalized === 'silent' || normalized === 'headless') {
    return normalized
  }
  return headless ? 'headless' : 'normal'
}

export const normalizeTempMailProvider = (
  value: string | undefined,
): RefreshSettings['temp_mail_provider'] => {
  const normalized = value?.trim().toLowerCase()
  if (
    normalized === 'duckmail'
    || normalized === 'moemail'
    || normalized === 'freemail'
    || normalized === 'gptmail'
    || normalized === 'cfmail'
  ) {
    return normalized
  }
  return 'duckmail'
}

export const normalizeImageOutputFormat = (value: string | undefined): 'base64' | 'url' =>
  value?.trim().toLowerCase() === 'url' ? 'url' : 'base64'

export const normalizeVideoOutputFormat = (
  value: string | undefined,
): 'html' | 'url' | 'markdown' => {
  const normalized = value?.trim().toLowerCase()
  if (normalized === 'url' || normalized === 'markdown') {
    return normalized
  }
  return 'html'
}

export const normalizeStringArray = (values: Array<string | undefined> | undefined) => {
  if (!Array.isArray(values)) {
    return []
  }

  const next: string[] = []
  const seen = new Set<string>()

  for (const value of values) {
    if (typeof value !== 'string') {
      continue
    }

    const normalized = value.trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }

    seen.add(normalized)
    next.push(normalized)
  }

  return next
}

export const toCooldownHours = (seconds: number | undefined, fallbackHours: number) => {
  if (!Number.isFinite(seconds)) return fallbackHours
  return Math.max(1, Math.round(Number(seconds) / 3600))
}
