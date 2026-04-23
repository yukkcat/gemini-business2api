import { DEFAULT_RETRY_SETTINGS } from './settingsDefaults'

export const DEFAULT_COOLDOWN_HOURS = {
  text: DEFAULT_RETRY_SETTINGS.text_rate_limit_cooldown_seconds / 3600,
  images: DEFAULT_RETRY_SETTINGS.images_rate_limit_cooldown_seconds / 3600,
  videos: DEFAULT_RETRY_SETTINGS.videos_rate_limit_cooldown_seconds / 3600,
} as const

export const browserModeOptions = [
  { label: 'normal - 正常窗口', value: 'normal' },
  { label: 'silent - 静默窗口', value: 'silent' },
  { label: 'headless - 无头', value: 'headless' },
]

export const tempMailProviderOptions = [
  { label: 'DuckMail', value: 'duckmail' },
  { label: 'Moemail', value: 'moemail' },
  { label: 'Freemail', value: 'freemail' },
  { label: 'GPTMail', value: 'gptmail' },
  { label: 'Cloudflare Mail', value: 'cfmail' },
]

export const imageOutputOptions = [
  { label: 'Base64 编码', value: 'base64' },
  { label: 'URL 链接', value: 'url' },
]

export const videoOutputOptions = [
  { label: 'HTML 视频标签', value: 'html' },
  { label: 'URL 链接', value: 'url' },
  { label: 'Markdown 格式', value: 'markdown' },
]
