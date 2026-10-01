<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { FactorySummary } from '../lib/types'
import { fetchFactories } from '../lib/api'
import { fmtCost, fmtDate, fmtTokens, ts } from '../lib/format'
import { hrefFor } from '../lib/router'
import StatusChip from './StatusChip.vue'

// Dashboard over data the page already has: /api/factories aggregates plus a
// reachability ping per ecosystem service. No new server route.
const factories = shallowRef<FactorySummary[]>([])
const host = `${location.protocol}//${location.hostname}`
const services = [
  { name: 'OmniRoute', port: 20128, path: '/api/health' },
  { name: 'SSLF API', port: 3001, path: '/health' },
  { name: 'SSLF Web', port: 5173, path: '/' },
  { name: 'SSBF API', port: 4700, path: '/health' },
  { name: 'SSBF Web', port: 4701, path: '/' },
  { name: 'SSTT', port: 4800, path: '/health' },
  { name: 'DSH', port: 3080, path: '/' },
]
const up = ref<Record<string, boolean | null>>({})

// no-cors: an opaque response still proves the port answered; only a network
// failure rejects — which is exactly "down".
async function ping() {
  const entries = await Promise.all(services.map(async s => {
    try {
      await fetch(`${host}:${s.port}${s.path}`, { mode: 'no-cors', signal: AbortSignal.timeout(3000) })
      return [s.name, true] as const
    } catch {
      return [s.name, false] as const
    }
  }))
  up.value = Object.fromEntries(entries)
}

async function load() {
  try { factories.value = await fetchFactories() } catch {}
}

const runs = computed(() => factories.value
  .flatMap(f => f.recent_runs.map(r => ({ ...r, factory: f.name })))
  .toSorted((a, b) => (ts(b.started_at) || 0) - (ts(a.started_at) || 0))
  .slice(0, 12))
const sum = (key: 'session_count' | 'running_count' | 'total_cost' | 'total_tokens') =>
  factories.value.reduce((n, f) => n + (f[key] || 0), 0)
const done = computed(() => runs.value.filter(r => r.status === 'success' || r.status === 'fail'))
const successRate = computed(() => done.value.length
  ? `${Math.round(100 * done.value.filter(r => r.status === 'success').length / done.value.length)}%`
  : '—')
const servicesUp = computed(() => Object.values(up.value).filter(Boolean).length)

let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  void load()
  void ping()
  timer = setInterval(() => { void load(); void ping() }, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="overview">
    <div class="stats">
      <div class="stat"><small>Factories</small><strong>{{ factories.length }}</strong><span>{{ sum('session_count') }} runs total</span></div>
      <div class="stat"><small>Running now</small><strong :class="{ live: sum('running_count') }">{{ sum('running_count') }}</strong><span>active workflows</span></div>
      <div class="stat"><small>Success rate</small><strong>{{ successRate }}</strong><span>last {{ done.length }} finished runs</span></div>
      <div class="stat"><small>Spend</small><strong>{{ fmtCost(sum('total_cost')) }}</strong><span>{{ fmtTokens(sum('total_tokens')) }} tokens</span></div>
      <div class="stat"><small>Services</small><strong>{{ servicesUp }}/{{ services.length }}</strong><span>ecosystem up</span></div>
    </div>
    <div class="panels">
      <div class="panel">
        <div class="panel-head">Recent runs</div>
        <a v-for="r in runs" :key="`${r.factory}/${r.adw_id}`" class="row" :href="hrefFor(r.factory, r.adw_id)">
          <StatusChip :status="r.status ?? 'queued'" />
          <div class="main">
            <div class="title">{{ r.request || r.adw_name || r.adw_id }}</div>
            <div class="sub">{{ r.factory }} · {{ r.adw_name ?? 'adw' }} · {{ fmtCost(r.total_cost) }}</div>
          </div>
          <span class="meta">{{ fmtDate(r.started_at) }}</span>
        </a>
        <div v-if="!runs.length" class="empty">No runs yet — use “Run a workflow” to start one.</div>
      </div>
      <div class="panel">
        <div class="panel-head">Ecosystem services</div>
        <a v-for="s in services" :key="s.name" class="row" :href="`${host}:${s.port}/`" target="_blank">
          <span class="dot" :class="up[s.name] == null ? '' : up[s.name] ? 'on' : 'off'" />
          <div class="main"><div class="title">{{ s.name }}</div></div>
          <span class="meta">:{{ s.port }}</span>
        </a>
      </div>
    </div>
  </section>
</template>

<style scoped>
.overview { padding: 16px 24px 0; display: flex; flex-direction: column; gap: 16px; }
.stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.stat, .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; }
.stat { padding: 12px 16px; display: flex; flex-direction: column; }
.stat small { font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--faint); }
.stat strong { font-size: 26px; }
.stat strong.live { color: var(--green); }
.stat span { color: var(--dim); font-size: 14px; }
.panels { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }
.panel { overflow: hidden; max-height: 360px; overflow-y: auto; }
.panel-head { padding: 10px 16px; border-bottom: 1px solid var(--border-soft); font-weight: 700; }
.row { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid var(--border-soft); color: var(--text); }
.row:hover { background: var(--panel-2); }
.main { flex: 1; min-width: 0; }
.title, .sub { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sub, .meta { color: var(--faint); font-size: 14px; }
.meta { white-space: nowrap; font-family: var(--mono); }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--faint); }
.dot.on { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot.off { background: var(--red); }
.empty { padding: 14px 16px; color: var(--faint); }
</style>
