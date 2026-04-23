<template>
  <button
    type="button"
    role="checkbox"
    class="inline-flex items-center gap-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50"
    :aria-checked="ariaChecked"
    :aria-label="ariaLabel || label || '切换选择状态'"
    :disabled="disabled"
    @click="$emit('toggle')"
  >
    <span
      class="flex h-4 w-4 items-center justify-center rounded border transition-colors"
      :class="indicatorClass"
      aria-hidden="true"
    >
      <svg
        v-if="state === 'checked'"
        viewBox="0 0 20 20"
        class="h-3.5 w-3.5"
        fill="currentColor"
      >
        <path d="M7.6 13.2 4.4 10l1.2-1.2 2 2 6-6 1.2 1.2-7.2 7.2z" />
      </svg>
      <svg
        v-else-if="state === 'indeterminate'"
        viewBox="0 0 20 20"
        class="h-3.5 w-3.5"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      >
        <path d="M5 10h10" />
      </svg>
    </span>
    <span v-if="label" class="text-xs text-muted-foreground">
      {{ label }}
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  state: 'unchecked' | 'indeterminate' | 'checked'
  label?: string
  ariaLabel?: string
  disabled?: boolean
}>()

defineEmits<{
  (e: 'toggle'): void
}>()

const ariaChecked = computed(() => (props.state === 'indeterminate' ? 'mixed' : String(props.state === 'checked')))

const indicatorClass = computed(() => {
  if (props.state === 'checked' || props.state === 'indeterminate') {
    return 'border-foreground bg-foreground text-white'
  }
  return 'border-border bg-background text-transparent'
})
</script>
