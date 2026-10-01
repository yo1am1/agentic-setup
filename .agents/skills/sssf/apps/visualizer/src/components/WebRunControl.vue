<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { WebRunDetail } from '../lib/types'
import { fetchWebRun, stopWebRun } from '../lib/api'

const props = defineProps<{ factory: string; adwId: string }>()
const run = ref<WebRunDetail | null>(null)
const error = ref('')
const stopping = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

async function tick() {
  if (inflight || stopping.value) return
  inflight = true
  try { run.value = await fetchWebRun(props.factory, props.adwId); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { inflight = false }
}

async function stop() {
  stopping.value = true
  try { run.value = await stopWebRun(props.factory, props.adwId); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { stopping.value = false }
}

onMounted(() => { void tick(); timer = setInterval(tick, 1000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section v-if="run || error" class="web-run" aria-label="Workflow launch controls">
    <div v-if="run" class="run-head">
      <span aria-live="polite">Web launch: {{ run.status }}{{ run.exit_code !== null ? ` · exit ${run.exit_code}` : '' }}</span>
      <button v-if="['starting', 'running', 'stopping'].includes(run.status)" type="button"
        :disabled="stopping || run.status === 'stopping'" @click="stop">Stop workflow</button>
    </div>
    <p v-if="run?.error || error" role="alert">{{ error || run?.error }}</p>
    <details v-if="run?.output" :open="['fail', 'interrupted', 'cancelled'].includes(run.status)">
      <summary>Launch output (last 16 KB)</summary>
      <pre>{{ run.output }}</pre>
    </details>
    <p v-if="run?.status === 'starting' || run?.status === 'running'" class="dim">The trace appears once the Python workflow starts. Launch output includes startup errors.</p>
  </section>
</template>

<style scoped>
.web-run { margin: 16px 24px; padding: 16px; border: 1px solid var(--border-soft); border-radius: 12px; background: var(--surface); }
.run-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
button { color: var(--text); font: inherit; background: var(--bg); border: 1px solid var(--border-soft); border-radius: 8px; padding: 8px 12px; cursor: pointer; }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--cyan); outline-offset: 3px; }
button:disabled { opacity: .5; }
details { margin-top: 12px; }
summary { cursor: pointer; }
pre { max-height: 320px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 13px var(--mono); }
</style>
