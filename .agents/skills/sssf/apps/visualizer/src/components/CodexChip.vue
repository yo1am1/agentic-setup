<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RotateCw } from 'lucide-vue-next'
import type { CodexUsage, CodexWindow } from '../lib/types'

const props = withDefaults(
  defineProps<{
    usage: CodexUsage | null
    loading: boolean
    label?: string
  }>(),
  { label: 'codex' },
)
const emit = defineEmits<{ refresh: [] }>()

/** Shortest window first: the 5h session is the one that stops work today, the
 *  weekly ceiling is the one that stops work this week. Every provider chip
 *  reads the same way, so two of them side by side can be compared at a glance. */
const orderedWindows = computed(() =>
  props.usage ? props.usage.windows.toSorted((a, b) => a.window_seconds - b.window_seconds) : [],
)

/** The top bar button shows the headline windows (the primary model group if grouped). */
const chipWindows = computed(() => {
  const wins = orderedWindows.value
  if (!wins.some((w) => w.group)) return wins
  const firstGroup = wins[0]?.group
  return wins.filter((w) => w.group === firstGroup)
})

function windowLeft(used: number): number {
  return Math.max(0, 100 - used)
}

function compactLabel(label: string): string {
  return label === 'weekly' ? '7d' : label === 'daily' ? '1d' : label
}

/** "5d" / "18h" / "40m" — how long until the headline window rolls over. */
function until(resetAt: number): string {
  const ms = resetAt * 1000 - Date.now()
  if (!Number.isFinite(ms) || ms <= 0) return 'now'
  const hours = Math.floor(ms / 3_600_000)
  if (hours >= 24) return `${Math.floor(hours / 24)}d`
  if (hours >= 1) return `${hours}h`
  return `${Math.max(1, Math.round(ms / 60_000))}m`
}

// ── Popover ──────────────────────────────────────────────────────────────────

/** The window's own name, derived from its length, not the provider's slot. */
function windowName(w: CodexWindow): string {
  let name = w.label
  if (w.window_seconds <= 6 * 3600) name = 'Current session'
  else if (w.window_seconds <= 26 * 3600) name = 'Today'
  else if (w.window_seconds <= 8 * 86400) name = 'This week'
  return w.group ? `${w.group} · ${name}` : name
}

/** "at 4:00 PM" today, "Monday 5:00 AM" this week, "Sep 16, 1:45 PM" beyond. */
function resetLabel(resetAt: number): string {
  const date = new Date(resetAt * 1000)
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (date.toDateString() === new Date().toDateString()) return `at ${time}`
  if (date.getTime() - Date.now() < 7 * 86_400_000) {
    return `${date.toLocaleDateString([], { weekday: 'long' })} ${time}`
  }
  return `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${time}`
}

type Level = 'ok' | 'warn' | 'critical'

/** Severity of one window, read off what REMAINS so thresholds tighten as it drains. */
function levelOf(w: CodexWindow): Level {
  const left = windowLeft(w.used_percent)
  if (left <= 5) return 'critical'
  if (left <= 20) return 'warn'
  return 'ok'
}

const levelLeft = computed(() =>
  orderedWindows.value.length
    ? Math.min(...orderedWindows.value.map((window) => windowLeft(window.used_percent)))
    : null,
)

// Thresholds read off what remains, so they tighten as the quota drains.
const level = computed<Level>(() => {
  if (levelLeft.value === null) return 'ok'
  if (levelLeft.value <= 5) return 'critical'
  if (levelLeft.value <= 20) return 'warn'
  return 'ok'
})

/** No usage and not loading means the read failed outright (bad creds, no
 *  network, upstream shape changed) — distinct from the brief window while
 *  the first read is still in flight. */
const failed = computed(() => !props.usage && !props.loading)

const ariaLabel = computed(() => {
  if (props.loading) return `Checking ${props.label} quota…`
  if (!props.usage) return `${props.label} quota unavailable — click to retry`
  const worst = orderedWindows.value[0]
  const summary = worst
    ? `${worst.used_percent}% of the ${windowName(worst).toLowerCase()} quota used`
    : 'quota unknown'
  return `${props.label}: ${summary}. Click to refresh.`
})

const readAt = computed(() =>
  props.usage ? new Date(props.usage.as_of).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '',
)

// The popover is CSS :hover/:focus-within only, which touch devices have
// neither of — on a phone there was no way to ever see it. `pinned` gives
// tap an explicit open/close on top of the existing hover/focus behavior,
// closed by tapping outside, tapping the chip again, or Escape.
const root = ref<HTMLElement | null>(null)
const pinned = ref(false)

function onTrigger() {
  emit('refresh')
  pinned.value = !pinned.value
}

function onOutside(e: MouseEvent) {
  if (pinned.value && root.value && !root.value.contains(e.target as Node)) pinned.value = false
}

function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') pinned.value = false
}

onMounted(() => {
  document.addEventListener('click', onOutside)
  document.addEventListener('keydown', onEscape)
})

onUnmounted(() => {
  document.removeEventListener('click', onOutside)
  document.removeEventListener('keydown', onEscape)
})
</script>

<template>
  <span class="usage" ref="root">
    <button
      class="codex"
      :class="[level, { busy: loading, failed }]"
      type="button"
      :aria-label="ariaLabel"
      :aria-expanded="pinned"
      :disabled="loading"
      @click="onTrigger"
    >
      <span class="label">{{ label }}</span>

      <template v-if="chipWindows.length">
        <template v-for="(window, index) in chipWindows" :key="(window.group ?? '') + ':' + window.label">
          <span v-if="index > 0" class="sep">|</span>
          <span class="unit">{{ compactLabel(window.label) }}</span>
          <!-- Used, not remaining: the popover under this button has always read
               "% used", and two opposite readings of one number in one component
               is how "100%" came to mean a full tank on one line and an empty one
               on the next. Fresh window = 0%, exhausted = 100%. -->
          <span class="pct">{{ window.used_percent }}%</span>
          <span class="reset">{{ window.reset_at ? until(window.reset_at) : '—' }}</span>
        </template>
        <span v-if="usage!.source === 'cached'" class="stale">cached</span>
      </template>
      <span v-else-if="failed" class="pct failed-text">unavailable</span>
      <span v-else class="pct">…</span>

      <!-- Spins only while a read is in flight, so a refresh is visibly doing
           something even when the number it returns is unchanged. -->
      <RotateCw class="spin" :class="{ turning: loading }" :size="15" :stroke-width="2.4" />
    </button>

    <div v-if="usage" class="usage-pop" :class="{ pinned }" role="tooltip">
      <div v-for="window in orderedWindows" :key="(window.group ?? '') + ':' + window.label" class="u-row">
        <div class="u-head">
          <span class="u-name">{{ windowName(window) }}</span>
          <span class="u-used" :class="levelOf(window)">{{ window.used_percent }}% used</span>
        </div>
        <div class="u-sub">{{ window.reset_at ? `Resets ${resetLabel(window.reset_at)} · in ${until(window.reset_at)}` : 'No reset scheduled — starts counting on next use' }}</div>
        <div class="u-bar">
          <span class="u-fill" :class="levelOf(window)" :style="{ width: `${window.used_percent}%` }" />
        </div>
      </div>
      <div class="u-foot">
        <span>{{ usage.plan ?? 'unknown' }} plan</span>
        <span v-if="usage.source === 'live'">read live at {{ readAt }}</span>
        <span v-else class="u-cached">cached reading from {{ readAt }} — the live check failed</span>
        <span class="u-hint">click the chip to refresh</span>
      </div>
    </div>
  </span>
</template>

<style scoped>
.usage {
  position: relative;
  display: inline-flex;
}

/* Same pill geometry as StatChip, same row as the live hint — a status readout,
   not a new kind of object. A button because it is clickable, stripped back to
   look like the chip it replaced. */
.codex {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: rgba(19, 26, 38, 0.6);
  color: var(--text);
  font-family: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease;
}

.codex:hover:not(:disabled) {
  border-color: rgba(148, 163, 255, 0.45);
}

.codex:disabled {
  cursor: progress;
}

.label,
.sep,
.unit {
  color: var(--faint);
}

.pct {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.reset {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  color: var(--dim);
}

/* Colour arrives only as the quota actually runs low. */
.codex.warn {
  border-color: rgba(232, 182, 74, 0.5);
}

.codex.warn .pct {
  color: var(--yellow, #e8b64a);
}

.codex.critical {
  border-color: rgba(255, 111, 103, 0.6);
  background: rgba(255, 111, 103, 0.1);
}

.codex.critical .pct {
  color: var(--red);
}

/* Dashed border reads as "unavailable, click to retry" — distinct from the
   solid warn/critical borders, which mean "quota is real and running low". */
.codex.failed {
  border-style: dashed;
  border-color: var(--faint);
}

.failed-text {
  color: var(--faint);
}

.stale {
  color: var(--faint);
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.spin {
  color: var(--faint);
  flex: none;
}

.spin.turning {
  animation: codex-spin 0.9s linear infinite;
}

@keyframes codex-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── Hover popover: one bar per window, the way the subscription page shows
      them. Anchored to the chip's right edge so it never leaves the viewport. */
/* Centered under the chip rather than anchored to its right edge: a
   fixed-width popover pinned to `right: 0` ran off the left of the viewport
   any time the browser window was narrower than chip-position + 360px — not
   just on a phone, reproduced at 956px wide too. Centering plus clamping the
   width to the viewport keeps it fully on-screen regardless of where the
   chip lands or how narrow the window is. */
.usage-pop {
  position: absolute;
  top: calc(100% + 10px);
  left: 50%;
  z-index: 40;
  width: min(360px, calc(100vw - 32px));
  padding: 16px 18px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
  gap: 16px;
  opacity: 0;
  visibility: hidden;
  transform: translate(-50%, -4px);
  transition:
    opacity 0.15s ease,
    transform 0.15s ease,
    visibility 0.15s;
}

.usage:hover .usage-pop,
.usage:focus-within .usage-pop,
.usage-pop.pinned {
  opacity: 1;
  visibility: visible;
  transform: translate(-50%, 0);
}

/* Centering still leaves the box hanging off the left edge once the chip is
   closer to it than half the popover. That is not a phone-only case: below
   about 1000px the topbar wraps, the chips move to the left of the bar, and a
   360px popover centered on one runs off — measured at 985px and at 375px.
   Dropping `position: relative` here hands the popover to the topbar (sticky,
   so it is a containing block) and it spans the bar instead, which is both
   guaranteed on-screen and easier to read at those widths. */
@media (max-width: 1000px) {
  .usage {
    position: static;
  }

  .usage-pop {
    left: 16px;
    right: 16px;
    width: auto;
    transform: translateY(-4px);
  }

  .usage:hover .usage-pop,
  .usage:focus-within .usage-pop,
  .usage-pop.pinned {
    transform: translateY(0);
  }
}

.u-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.u-name {
  font-size: 15px;
  font-weight: 600;
}

.u-used {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--dim);
}

.u-used.warn {
  color: var(--yellow, #e8b64a);
}

.u-used.critical {
  color: var(--red);
}

.u-sub {
  margin-top: 2px;
  font-size: 13px;
  color: var(--faint);
}

.u-bar {
  margin-top: 8px;
  height: 6px;
  border-radius: 999px;
  background: rgba(6, 8, 15, 0.75);
  border: 1px solid var(--border-soft);
  overflow: hidden;
}

.u-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--blue);
  transition: width 300ms ease;
}

.u-fill.warn {
  background: var(--yellow, #e8b64a);
}

.u-fill.critical {
  background: var(--red);
}

.u-foot {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 10px;
  border-top: 1px solid var(--border-soft);
  font-size: 12px;
  color: var(--faint);
}

.u-cached {
  color: var(--yellow, #e8b64a);
}

.u-hint {
  color: var(--faint);
}
</style>
