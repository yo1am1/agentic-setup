<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { FactorySummary } from '../lib/types'
import { fetchFactories, fetchHealth } from '../lib/api'
import { ts } from '../lib/format'
import FactoryCard from './FactoryCard.vue'

const factories = shallowRef<FactorySummary[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const nowMs = ref(Date.now())
// Discovery is depth-1 under the scanned roots, so a factory stamped anywhere
// else is simply absent — no error, nothing to notice. Naming them turns that
// silence into an answer: this list is complete FOR THESE ROOTS, and a repo you
// expected to see lives outside them.
const roots = ref<string[]>([])

let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

async function tick() {
  if (inflight) return
  inflight = true
  try {
    factories.value = await fetchFactories()
    nowMs.value = Date.now()
    apiError.value = null
    loaded.value = true
  } catch (err) {
    apiError.value = err instanceof Error ? err.message : String(err)
  } finally {
    inflight = false
  }
}

onMounted(() => {
  void tick()
  timer = setInterval(() => void tick(), 500)
  // Once, not per poll: the root is fixed for the life of the server process.
  // A failure here costs the label and nothing else, so it stays silent.
  void fetchHealth()
    .then((health) => (roots.value = health.roots ?? []))
    .catch(() => undefined)
})

onUnmounted(() => clearInterval(timer))

// Busy factories first, then most recently active — what you came to look at
// should not be somewhere in an alphabetical list.
const ordered = computed(() =>
  factories.value.toSorted((a, b) => {
    if ((b.running_count > 0 ? 1 : 0) !== (a.running_count > 0 ? 1 : 0)) {
      return (b.running_count > 0 ? 1 : 0) - (a.running_count > 0 ? 1 : 0)
    }
    return (ts(b.last_started_at) || 0) - (ts(a.last_started_at) || 0)
  }),
)
</script>

<template>
  <div class="factories">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div v-if="ordered.length" class="list-head dim">
      {{ ordered.length }} factories
      <span v-if="roots.length" class="root">in {{ roots.join('  ·  ') }}</span>
    </div>

    <div v-if="ordered.length" class="cards">
      <FactoryCard v-for="f in ordered" :key="f.name" :factory="f" :now-ms="nowMs" />
    </div>
    <div v-else-if="loaded" class="empty-state">
      no factories in {{ roots.length ? roots.join(', ') : 'the scanned roots' }} — run `just
      factory` in a repo under one of them to make it launchable here
    </div>
    <div v-else-if="!apiError" class="empty-state">loading factories…</div>
  </div>
</template>

<style scoped>
/* Same metrics as SessionsList: one card language across both levels. */
.factories {
  display: flex;
  flex-direction: column;
}

.list-head {
  padding: 16px 24px 0;
  font-size: 16px;
}

/* Quieter than the count: the answer to "why is my repo not here", not a
   headline. Monospace because it is a path. */
.root {
  margin-left: 8px;
  font-family: var(--mono);
  color: var(--faint);
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(460px, 100%), 1fr));
  gap: 18px;
  padding: 16px 24px 28px;
}
</style>
