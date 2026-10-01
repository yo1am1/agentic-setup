<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  storageKey: string
  label: string
  controls: string
  defaultSize: number
  minSize: number
  minOther: number
  narrowAt?: number
}>()
const emit = defineEmits<{ resize: [size: number] }>()
const handle = ref<HTMLElement | null>(null)
const size = ref(props.defaultSize)
const narrow = ref(false)
let start = 0
let original = 0

const extent = () => narrow.value ? handle.value?.parentElement?.clientHeight ?? 0 : handle.value?.parentElement?.clientWidth ?? 0
const maximum = ref(props.defaultSize)
const minimum = ref(props.minSize)
function setSize(value: number) {
  size.value = Math.min(maximum.value, Math.max(minimum.value, value))
  emit('resize', size.value)
  localStorage.setItem(props.storageKey, String(size.value))
}
function updateBounds() {
  narrow.value = matchMedia(`(max-width: ${props.narrowAt ?? 700}px)`).matches
  maximum.value = Math.max(0, extent() - props.minOther - 8)
  minimum.value = Math.min(props.minSize, maximum.value)
  setSize(size.value)
}
function pointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  start = narrow.value ? event.clientY : event.clientX
  original = size.value
  handle.value?.setPointerCapture(event.pointerId)
  event.preventDefault()
}
function pointerMove(event: PointerEvent) {
  if (!handle.value?.hasPointerCapture(event.pointerId)) return
  setSize(original + (narrow.value ? event.clientY : event.clientX) - start)
}
function keyDown(event: KeyboardEvent) {
  const step = event.shiftKey ? 50 : 10
  const delta = narrow.value
    ? event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0
    : event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0
  if (!delta && event.key !== 'Home' && event.key !== 'End') return
  event.preventDefault()
  setSize(event.key === 'Home' ? minimum.value : event.key === 'End' ? maximum.value : size.value + delta)
}
onMounted(() => {
  const saved = Number(localStorage.getItem(props.storageKey))
  if (Number.isFinite(saved) && saved > 0) size.value = saved
  updateBounds()
  window.addEventListener('resize', updateBounds)
})
onUnmounted(() => window.removeEventListener('resize', updateBounds))
</script>

<template>
  <div
    ref="handle"
    class="splitter"
    role="separator"
    tabindex="0"
    :aria-label="label"
    :aria-controls="controls"
    :aria-orientation="narrow ? 'horizontal' : 'vertical'"
    :aria-valuemin="minimum"
    :aria-valuemax="maximum"
    :aria-valuenow="size"
    :aria-valuetext="`${size} pixels`"
    title="Drag to resize · arrow keys to adjust · double-click to reset"
    @pointerdown="pointerDown"
    @pointermove="pointerMove"
    @keydown="keyDown"
    @dblclick="setSize(defaultSize)"
  />
</template>

<style scoped>
/* Same splitter as SSTT: invisible 2px line, 10px hit area, cyan on hover/focus/drag. */
.splitter { position: relative; z-index: 6; justify-self: center; align-self: stretch; width: 2px; cursor: col-resize; touch-action: none; outline: none; }
.splitter::before { content: ''; position: absolute; inset: 0 -4px; }
.splitter::after { content: ''; position: absolute; inset: 0 -1px; border-radius: 2px; transition: background .15s; }
.splitter:hover::after, .splitter:focus-visible::after, .splitter:active::after { background: var(--cyan); }
.splitter[aria-orientation="horizontal"] { width: auto; height: 2px; justify-self: stretch; align-self: center; cursor: row-resize; }
.splitter[aria-orientation="horizontal"]::before { inset: -4px 0; }
.splitter[aria-orientation="horizontal"]::after { inset: -1px 0; }
</style>
