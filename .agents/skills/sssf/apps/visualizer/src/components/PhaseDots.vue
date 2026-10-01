<script setup lang="ts">
import { computed } from 'vue'
import type { Phase } from '../lib/types'

const props = defineProps<{ phases: Phase[] }>()

const ordered = computed(() => props.phases.toSorted((a, b) => (a.seq ?? 0) - (b.seq ?? 0)))

const glyph: Record<string, string> = {
  success: '●',
  running: '◐',
  queued: '○',
  fail: '✗',
}
</script>

<template>
  <span class="dots">
    <span
      v-for="p in ordered"
      :key="p.phase_id"
      class="d"
      :class="p.status"
      :title="`${p.name} — ${p.status}`"
      >{{ glyph[p.status ?? ''] ?? '○' }}</span
    >
    <span v-if="!ordered.length" class="faint">—</span>
  </span>
</template>

<style scoped>
/* One dot per phase, so a long run's row grows without bound. Everywhere this
   sits in a flex row it shares that row with something there is only one of —
   a timestamp, a duration — and unconstrained it pushed those clean off the
   card. Losing the tail of a repeated glyph is the cheapest thing in the row. */
.dots {
  display: inline-flex;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
  font-size: 16px;
  letter-spacing: 0;
}

.d.success {
  color: var(--green);
}

.d.fail {
  color: var(--red);
}

.d.running {
  color: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}

.d.queued {
  color: var(--faint);
}
</style>
