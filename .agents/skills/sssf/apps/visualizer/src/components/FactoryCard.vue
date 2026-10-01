<script setup lang="ts">
import { computed } from 'vue'
import type { FactorySummary, SessionSummary } from '../lib/types'
import { fmtDate, fmtDuration, ts } from '../lib/format'
import { agentColor } from '../lib/events'
import { hrefFor } from '../lib/router'
import PhaseDots from './PhaseDots.vue'
import StatChip from './StatChip.vue'

const props = defineProps<{ factory: FactorySummary; nowMs: number }>()

// No self-polling here, unlike SessionCard's per-run event tail: the index
// endpoint already batches every factory's runs into one response, so a card
// per repo polling its own endpoint would undo that.

const running = computed(() => props.factory.running_count > 0)

/**
 * The agent working right now is the owner of the phase that is running —
 * the same fact the waterfall draws, available without touching events.
 */
function activeAgent(run: SessionSummary): { name: string; color: string } | null {
  const phase = (run.phases ?? []).find((p) => p.status === 'running' && p.kind === 'agent')
  if (!phase?.owner) return null
  const index = (run.agents ?? []).findIndex((a) => a.agent === phase.owner)
  const info = index === -1 ? undefined : run.agents[index]
  return { name: phase.owner, color: agentColor(info?.color, null, Math.max(index, 0)) }
}

/** A finished run reports its own duration; a live one counts up. */
function elapsed(run: SessionSummary): number {
  const start = ts(run.started_at)
  if (!Number.isFinite(start)) return NaN
  const end = run.status === 'running' ? props.nowMs : ts(run.ended_at)
  return (Number.isFinite(end) ? end : props.nowMs) - start
}

const runs = computed(() =>
  props.factory.recent_runs.map((run) => ({
    run,
    agent: activeAgent(run),
    duration: elapsed(run),
  })),
)
</script>

<template>
  <a class="card" :class="{ running }" :href="hrefFor(factory.name)">
    <span class="card-head">
      <span class="card-id">{{ factory.name }}</span>
      <span v-if="running" class="running-pill">
        <span class="running-dot" />
        {{ factory.running_count }} running
      </span>
    </span>
    <span class="card-path" :title="factory.path">{{ factory.path }}</span>

    <div class="runs">
      <template v-if="runs.length">
        <div v-for="r in runs" :key="r.run.adw_id" class="run" :class="r.run.status ?? ''">
          <span class="run-id">{{ r.run.adw_id }}</span>
          <span class="run-adw" :title="r.run.request ?? ''">{{ r.run.adw_name ?? '—' }}</span>
          <PhaseDots :phases="r.run.phases ?? []" />
          <!-- While a run is live the useful thing is WHO is working, not how
               long it has been going; the clock returns once it finishes. -->
          <span v-if="r.agent" class="run-agent" :style="{ color: r.agent.color }">{{
            r.agent.name
          }}</span>
          <span v-else class="run-time dim">{{ fmtDuration(r.duration) }}</span>
        </div>
      </template>
      <div v-else class="runs-empty faint">no runs yet — stamped, never used</div>
    </div>

    <div class="card-foot">
      <span class="dim">{{ running ? 'started' : 'last run' }}</span>
      <span class="dim">{{ fmtDate(factory.last_started_at) }}</span>
    </div>
    <div class="card-stats">
      <StatChip kind="runs" :value="factory.session_count" />
      <StatChip kind="cost" :value="factory.total_cost" />
      <StatChip kind="tokens" :value="factory.total_tokens" />
    </div>
  </a>
</template>

<style scoped>
/* Same card language AND the same fixed height as SessionCard: the two grids
   never share a screen, but keeping the geometry identical means navigating
   factories → sessions does not resize everything under the cursor. The extra
   room over a 300px card is spent on more run rows, never on padding. */
.card {
  height: 420px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px 22px;
  position: relative;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  overflow: hidden;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.card:hover {
  border-color: rgba(148, 163, 255, 0.45);
  box-shadow: 0 10px 34px rgba(148, 163, 255, 0.12);
  transform: translateY(-2px);
}

.card.running {
  border-color: rgba(108, 182, 255, 0.6);
  box-shadow: 0 0 22px rgba(108, 182, 255, 0.16);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex: none;
}

.card-id {
  font-family: var(--mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--purple);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Plain LTR truncation on purpose: the rtl trick that keeps a path's tail
   visible also reorders its leading slash, and the tail here is the repo name,
   which the line above already shows in full. */
.card-path {
  flex: none;
  font-family: var(--mono);
  font-size: 16px;
  color: var(--cyan);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Fixed region, like SessionCard's timeline: eight 30px row slots, so a card
   with one run is exactly as tall as a card with eight. The server sends
   exactly this many runs — RECENT_RUNS_ON_CARD in db.ts. */
.runs {
  display: flex;
  flex-direction: column;
  margin-top: 2px;
  height: 240px;
  flex: none;
  overflow: hidden;
}

.run {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 30px;
  font-size: 16px;
  border-bottom: 1px solid var(--border-soft);
}

.run:last-child {
  border-bottom: none;
}

.run-id {
  flex: none;
  font-family: var(--mono);
  color: var(--purple);
}

.run-adw {
  flex: 1;
  min-width: 0;
  font-family: var(--mono);
  color: var(--cyan);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* A failed run should be findable without reading it — the id carries the
   signal, the way the sessions grid tints a whole failed card. */
.run.fail .run-id {
  color: var(--red);
}

.run-agent,
.run-time {
  flex: none;
  width: 74px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-agent {
  animation: pulse 1.6s ease-in-out infinite;
}

.run-time {
  font-family: var(--mono);
}

.runs-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 16px;
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: auto;
  font-size: 16px;
}

/* Mirrors StatusChip's pill geometry, but counts runs rather than naming one
   status — a factory has no single status to show. */
.running-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: none;
  padding: 3px 12px;
  border: 1px solid rgba(108, 182, 255, 0.45);
  border-radius: 999px;
  background: rgba(108, 182, 255, 0.12);
  color: var(--text);
  font-size: 16px;
  white-space: nowrap;
}

.running-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--blue);
  box-shadow: 0 0 10px rgba(108, 182, 255, 0.7);
  animation: pulse 1.6s ease-in-out infinite;
}

.card-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

/* Matching SessionCard: one column on a phone, so the fixed height aligns
   nothing and only clips the last stat chip. Content sizes the card there. */
@media (max-width: 640px) {
  .card {
    height: auto;
  }

  .runs {
    height: auto;
  }
}
</style>
