<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { SessionSummary } from '../lib/types'
import { fetchSessions } from '../lib/api'
import { ts } from '../lib/format'
import SessionCard from './SessionCard.vue'

const props = defineProps<{ factory: string }>()

const sessions = shallowRef<SessionSummary[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const nowMs = ref(Date.now())

let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

/**
 * Runs dismissed here but not yet dropped by the server's own list.
 *
 * Archiving is optimistic, and this list is replaced wholesale twice a second
 * — including by a response that was already in flight when the click landed,
 * which still carries the run. Filtering every response through this is what
 * stops a dismissed card reappearing a beat later. An id leaves as soon as the
 * server stops sending it, so this never hides anything on its own authority.
 */
const dismissed = new Set<string>()

function withoutDismissed(rows: SessionSummary[]): SessionSummary[] {
  for (const id of dismissed) {
    if (!rows.some((s) => s.adw_id === id)) dismissed.delete(id)
  }
  return dismissed.size ? rows.filter((s) => !dismissed.has(s.adw_id)) : rows
}

async function tick() {
  if (inflight) return
  inflight = true
  try {
    sessions.value = withoutDismissed(await fetchSessions(props.factory))
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
})

onUnmounted(() => clearInterval(timer))

function onArchived(adwId: string) {
  dismissed.add(adwId)
  sessions.value = sessions.value.filter((s) => s.adw_id !== adwId)
}

/** The write failed — let the run come back rather than hiding it on a lie. */
function onArchiveFailed(adwId: string) {
  dismissed.delete(adwId)
  void tick()
}

const ordered = computed(() =>
  sessions.value.toSorted((a, b) => (ts(b.started_at) || 0) - (ts(a.started_at) || 0)),
)
</script>

<template>
  <div class="sessions">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div v-if="ordered.length" class="list-head dim">{{ ordered.length }} runs</div>

    <div v-if="ordered.length" class="cards">
      <SessionCard
        v-for="s in ordered"
        :key="s.adw_id"
        :factory="factory"
        :session="s"
        :now-ms="nowMs"
        @archived="onArchived"
        @archive-failed="onArchiveFailed"
      />
    </div>
    <div v-else-if="loaded" class="empty-state">no sessions yet — run an ADW to see it here</div>
    <div v-else-if="!apiError" class="empty-state">loading sessions…</div>
  </div>
</template>

<style scoped>
.sessions {
  display: flex;
  flex-direction: column;
}

.list-head {
  padding: 16px 24px 0;
  font-size: 16px;
}

.cards {
  /* Uniform grid: every card the same width and (fixed in SessionCard) height,
     independent of content. */
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(460px, 100%), 1fr));
  gap: 18px;
  padding: 16px 24px 28px;
}





</style>
