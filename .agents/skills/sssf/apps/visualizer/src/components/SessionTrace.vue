<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue'
import type {
  AgentSession,
  AgentStartPayload,
  Envelope,
  EventRow,
  GateResult,
  Phase,
  PhaseKind,
  Session,
  SessionUsage,
} from '../lib/types'
import { Bot, FileText, SquareTerminal, UserRound } from 'lucide-vue-next'
import { mainEnvelope } from '../lib/outputs'
import EnvelopeOutput from './EnvelopeOutput.vue'
import { fetchEnvelopes, fetchEvents, fetchGates, fetchSession } from '../lib/api'
import { axisTicks, fmtDate, payloadOk, ts } from '../lib/format'
import { modelIcon, modelName } from '../lib/models'
import { agentColor, hexAlpha, parseAgentStart } from '../lib/events'
import { navigate, phaseCrumb } from '../lib/router'
import StatusChip from './StatusChip.vue'
import StatChip from './StatChip.vue'
import PhaseDetail from './PhaseDetail.vue'
import Splitter from './Splitter.vue'
import WebRunControl from './WebRunControl.vue'

const props = defineProps<{ factory: string; adwId: string; phaseId: string | null }>()
const phaseListSize = ref(480)

const session = ref<Session | null>(null)
const phases = ref<Phase[]>([])
const agents = ref<AgentSession[]>([])
const usage = ref<SessionUsage>({ read: 0, written: 0 })
const events = ref<EventRow[]>([])
const envelopes = ref<Envelope[]>([])
const gates = ref<GateResult[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const nowMs = ref(Date.now())

/**
 * The run's headline result, reachable without opening a phase.
 *
 * A Fusion run exists to produce one plan, and finding it meant knowing which
 * of a dozen blocks was the synthesis and clicking it. This is the same
 * EnvelopeOutput the phase view renders — the same panel, the same toggles —
 * just handed the run's own main envelope.
 */
const showOutput = ref(false)

const mainOutput = computed(() => {
  const seq = new Map(phases.value.map((p) => [p.phase_id, p.seq]))
  return mainEnvelope(envelopes.value, (id) => seq.get(id ?? '') ?? -1)
})

/** Which phase produced it, so the panel can say so and link there. */
const mainOutputPhase = computed(() =>
  phases.value.find((p) => p.phase_id === mainOutput.value?.phase_id) ?? null,
)

let cursor = 0
let inflight = false
let timer: ReturnType<typeof setInterval> | undefined

const SIDE_TABLE_TYPES = new Set(['gate_pass', 'gate_fail', 'handoff', 'agent_end', 'phase_end', 'error'])

async function tick() {
  if (inflight) return
  inflight = true
  try {
    const detail = await fetchSession(props.factory, props.adwId)
    session.value = detail.session
    phases.value = detail.phases.toSorted((a, b) => (a.seq ?? 0) - (b.seq ?? 0))
    agents.value = detail.agents
    usage.value = detail.usage

    const fresh: EventRow[] = []
    let page
    do {
      // Cursor pagination is inherently sequential: each request needs the previous cursor.
      // oxlint-disable-next-line no-await-in-loop
      page = await fetchEvents(props.factory, props.adwId, cursor, 1000)
      cursor = Math.max(cursor, page.cursor)
      fresh.push(...page.events)
    } while (page.has_more)
    if (fresh.length) events.value = [...events.value, ...fresh]

    // Envelopes and gates only gain rows around phase/agent boundaries — refetch
    // on those events instead of every tick.
    if (!loaded.value || fresh.some((e) => e.type !== null && SIDE_TABLE_TYPES.has(e.type))) {
      const [env, g] = await Promise.all([
        fetchEnvelopes(props.factory, props.adwId),
        fetchGates(props.factory, props.adwId),
      ])
      envelopes.value = env
      gates.value = g
    }

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

onUnmounted(() => {
  clearInterval(timer)
  phaseCrumb.value = null
})

const selectedPhase = computed(
  () => phases.value.find((p) => p.phase_id === props.phaseId) ?? null,
)

watchEffect(() => {
  phaseCrumb.value = selectedPhase.value?.name ?? null
})

// ── Lanes ────────────────────────────────────────────────────────────────────

const ENGINEER_COLOR = '#e8b64a'
const CODE_COLOR = '#5ad2dd'

const KIND_ICONS = { engineer: UserRound, code: SquareTerminal, agent: Bot }

interface Lane {
  id: string
  label: string
  /** Model driving this lane's agent — rendered with its provider icon. */
  model: string | null
  /** Context-window occupancy, or null while unknown (running / old db). */
  context: LaneContext | null
  metaLines: string[]
  color: string
  kind: PhaseKind
  phases: Phase[]
}

interface LaneContext {
  used: number
  window: number
  /** 0–100, uncapped by the floor applied to the bar's width. */
  pct: number
}

/** Occupancy for an agent lane. Null unless BOTH numbers are real — a bar
 *  against an unknown ceiling would be decoration, not data. */
function laneContext(info: AgentSession | undefined): LaneContext | null {
  const used = info?.context_tokens ?? 0
  const window = info?.context_window ?? 0
  if (!used || !window) return null
  return { used, window, pct: Math.min(100, (used / window) * 100) }
}

/** Sub-1% occupancy is common and real; round it away and the bar reads empty. */
function contextLabel(ctx: LaneContext): string {
  return ctx.pct < 1 ? `${ctx.pct.toFixed(1)}%` : `${Math.round(ctx.pct)}%`
}

/** Keep a non-zero fill visible — the exact numbers ride in the label and title. */
function contextFill(ctx: LaneContext): string {
  return `${Math.max(ctx.pct, 2)}%`
}

const NUM = new Intl.NumberFormat('en-US')

// A live agent's model/thinking/color arrive on its agent_start event before
// any agent_sessions row exists; attribute each start to its phase's owner.
const ownerStart = computed<Record<string, AgentStartPayload>>(() => {
  const ownerByPhase = new Map<string, string | null>(
    phases.value.map((p) => [p.phase_id, p.owner]),
  )
  const meta: Record<string, AgentStartPayload> = {}
  for (const e of events.value) {
    if (e.type !== 'agent_start') continue
    const owner = (e.phase_id ? ownerByPhase.get(e.phase_id) : null) ?? e.name
    if (!owner || meta[owner]) continue
    const payload = parseAgentStart(e)
    if (payload) meta[owner] = payload
  }
  return meta
})

const lanes = computed<Lane[]>(() => {
  const ph = phases.value
  const agentOwners: string[] = []
  for (const p of ph) {
    if (p.kind === 'agent' && p.owner && !agentOwners.includes(p.owner)) agentOwners.push(p.owner)
  }
  const codePhases = ph.filter((p) => p.kind === 'code')
  const out: Lane[] = [
    {
      id: 'engineer',
      label: session.value?.engineer ?? 'engineer',
      model: null,
      context: null,
      metaLines: ['engineer'],
      color: ENGINEER_COLOR,
      kind: 'engineer' as const,
      phases: ph.filter((p) => p.kind === 'engineer'),
    },
  ]
  if (codePhases.length) {
    out.push({
      id: 'code',
      label: 'code',
      model: null,
      context: null,
      metaLines: ['workspace'],
      color: CODE_COLOR,
      kind: 'code' as const,
      phases: codePhases,
    })
  }
  for (const [i, owner] of agentOwners.entries()) {
    const info = agents.value.find((a) => a.agent === owner)
    const start = ownerStart.value[owner]
    out.push({
      id: `agent:${owner}`,
      label: owner,
      // The model is the lane's whole story; thinking level lives in the
      // phase detail's agent config section.
      model: info?.model ?? start?.model ?? null,
      context: laneContext(info),
      metaLines: [],
      color: agentColor(info?.color, start?.color, i),
      kind: 'agent' as const,
      phases: ph.filter((p) => p.kind === 'agent' && p.owner === owner),
    })
  }
  return out
})

// ── Timeline geometry ────────────────────────────────────────────────────────

const range = computed(() => {
  let t0 = Infinity
  let t1 = -Infinity
  const s = session.value
  const sStart = ts(s?.started_at)
  const sEnd = ts(s?.ended_at)
  if (Number.isFinite(sStart)) t0 = Math.min(t0, sStart)
  if (Number.isFinite(sEnd)) t1 = Math.max(t1, sEnd)
  for (const p of phases.value) {
    const a = ts(p.started_at)
    const b = ts(p.ended_at)
    if (Number.isFinite(a)) {
      t0 = Math.min(t0, a)
      t1 = Math.max(t1, a)
    }
    if (Number.isFinite(b)) t1 = Math.max(t1, b)
  }
  if (s?.status === 'running') t1 = Math.max(t1, nowMs.value)
  if (!Number.isFinite(t0)) {
    t0 = nowMs.value
    t1 = t0 + 1000
  }
  if (t1 - t0 < 1000) t1 = t0 + 1000
  return { t0, t1, span: t1 - t0 }
})

// The engineer's request opens the run and owns the start of the timeline: it
// gets an exclusive leading zone, and every later phase maps into the rest —
// nothing can render on top of it.
const REQ_ZONE_PCT = 16

const requestPhase = computed(
  () => phases.value.find((p) => p.kind === 'engineer' && p.started_at) ?? null,
)

const zonePct = computed(() => (requestPhase.value ? REQ_ZONE_PCT : 0))

/**
 * Where the post-request timeline begins, in ms.
 *
 * The earliest non-engineer phase start, not the request phase's end: a later
 * ADW joining the session pushes the request row's ended_at forward, which
 * would otherwise throw every already-finished phase behind the origin.
 */
const originMs = computed(() => {
  const { t0 } = range.value
  const req = requestPhase.value
  if (!req) return t0
  let earliest = Infinity
  for (const p of phases.value) {
    if (p.kind === 'engineer') continue
    const s = ts(p.started_at)
    if (Number.isFinite(s)) earliest = Math.min(earliest, s)
  }
  if (Number.isFinite(earliest)) return Math.max(earliest, t0)
  const end = ts(req.ended_at ?? req.started_at)
  return Number.isFinite(end) ? Math.max(end, t0) : t0
})

const postSpan = computed(() => Math.max(range.value.t1 - originMs.value, 1000))

const ticks = computed(() => {
  const zone = zonePct.value
  return axisTicks(postSpan.value, 7).map((t) => ({
    pct: zone + (t.pct * (100 - zone)) / 100,
    label: t.label,
  }))
})

/**
 * Adjusted layout for every timed phase, in track-%.
 *
 * A phase only ever overlaps another phase IN ITS OWN LANE — a Fusion round
 * runs several agent lanes at once, same start time, side by side, not on
 * top of each other. So the near-zero-width floor and its rightward shift
 * (for a git commit or such) are computed per lane: widening one lane's
 * block must never push a block in a DIFFERENT lane off its true timestamp.
 * Doing this globally once staggered every parallel lane into a fake
 * staircase, as if every phase in the run were sequential. One scale factor
 * is still shared across all lanes afterward, so the top axis stays true.
 */
const MIN_BLOCK_PCT = 3.5

const blockLayout = computed<Record<string, { left: number; width: number }>>(() => {
  const zone = zonePct.value
  const avail = 100 - zone - 0.4 // hair of right margin
  const t0 = originMs.value
  const span = postSpan.value
  const reqId = requestPhase.value?.phase_id

  type Raw = { id: string; left: number; width: number }
  const laneRows: Raw[][] = []
  let maxEdge = avail

  for (const lane of lanes.value) {
    const timed = lane.phases
      .filter((p) => p.phase_id !== reqId && Number.isFinite(ts(p.started_at)))
      .map((p) => {
        const start = ts(p.started_at)
        let end = ts(p.ended_at)
        if (!Number.isFinite(end)) end = p.status === 'running' ? nowMs.value : start
        return {
          id: p.phase_id,
          start,
          left: ((start - t0) / span) * avail,
          width: ((Math.max(end, start) - start) / span) * avail,
        }
      })
      .toSorted((a, b) => a.start - b.start)

    let shift = 0
    let prevEdge = 0
    const rows: Raw[] = []
    for (const b of timed) {
      let left = b.left + shift
      if (left < prevEdge) {
        shift += prevEdge - left
        left = prevEdge
      }
      const width = Math.max(b.width, MIN_BLOCK_PCT)
      shift += width - b.width
      prevEdge = left + width
      rows.push({ id: b.id, left, width })
    }
    laneRows.push(rows)
    maxEdge = Math.max(maxEdge, prevEdge)
  }

  const scale = avail / maxEdge
  const out: Record<string, { left: number; width: number }> = {}
  for (const rows of laneRows) {
    for (const r of rows) out[r.id] = { left: zone + r.left * scale, width: r.width * scale }
  }
  return out
})

function blockGeom(p: Phase): { left: string; width: string } | null {
  // The request block fills its reserved zone, nothing else ever enters it.
  if (p.phase_id === requestPhase.value?.phase_id && zonePct.value > 0) {
    return { left: '0.4%', width: `${zonePct.value - 0.8}%` }
  }
  const geom = blockLayout.value[p.phase_id]
  if (!geom) return null
  return { left: `${geom.left}%`, width: `${geom.width}%` }
}

function blockStyle(p: Phase, lane: Lane): Record<string, string> | undefined {
  const geom = blockGeom(p)
  if (!geom) return undefined
  return {
    left: geom.left,
    width: geom.width,
    background: `linear-gradient(180deg, ${hexAlpha(lane.color, 0.2)}, ${hexAlpha(lane.color, 0.05)})`,
    borderColor: p.status === 'fail' ? 'rgba(255, 111, 103, 0.8)' : hexAlpha(lane.color, 0.55),
    '--lane-glow': hexAlpha(lane.color, 0.28),
  }
}

function blockDurationMs(p: Phase): number {
  const start = ts(p.started_at)
  if (!Number.isFinite(start)) return NaN
  const end = p.status === 'running' ? nowMs.value : ts(p.ended_at)
  if (!Number.isFinite(end)) return NaN
  return end - start
}

const STATUS_GLYPH: Record<string, string> = {
  success: '✓',
  fail: '✗',
  running: '●',
  queued: '○',
}

// Tool-call tick marks inside a phase block, positioned within the block's own span.
interface ToolTick {
  t: number
  ok: boolean
}

const toolTicks = computed(() => {
  const map: Record<string, ToolTick[]> = {}
  for (const e of events.value) {
    if (e.type !== 'tool_call' || !e.phase_id) continue
    map[e.phase_id] ??= []
    map[e.phase_id]?.push({ t: ts(e.started_at), ok: payloadOk(e.payload_json) })
  }
  return map
})

function ticksFor(p: Phase): { x: number; ok: boolean }[] {
  const start = ts(p.started_at)
  if (!Number.isFinite(start)) return []
  let end = ts(p.ended_at)
  if (!Number.isFinite(end)) end = p.status === 'running' ? nowMs.value : start
  const width = Math.max(end - start, 1)
  return (toolTicks.value[p.phase_id] ?? [])
    .filter((mark) => Number.isFinite(mark.t))
    .map((mark) => ({
      x: Math.min(Math.max(((mark.t - start) / width) * 100, 1), 99),
      ok: mark.ok,
    }))
}

const queuedByLane = computed(() => {
  const map: Record<string, Phase[]> = {}
  for (const lane of lanes.value) {
    map[lane.id] = lane.phases.filter((p) => !p.started_at)
  }
  return map
})

const sessionDurationMs = computed(() => {
  const s = session.value
  if (!s) return NaN
  const start = ts(s.started_at)
  if (!Number.isFinite(start)) return NaN
  const end = s.status === 'running' ? nowMs.value : ts(s.ended_at)
  return (Number.isFinite(end) ? end : nowMs.value) - start
})

function selectPhase(p: Phase) {
  navigate(props.factory, props.adwId, p.phase_id === props.phaseId ? null : p.phase_id)
}
</script>

<template>
  <WebRunControl v-if="adwId.startsWith('web-')" :factory="factory" :adw-id="adwId" />
  <div class="trace">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div v-if="session" class="run-strip">
      <span class="request" :title="session.request ?? ''">{{ session.request }}</span>
      <StatusChip :status="session.status ?? 'fail'" />
      <span class="dim">started {{ fmtDate(session.started_at) }}</span>
      <button
        v-if="mainOutput"
        type="button"
        class="output-btn"
        :class="{ on: showOutput }"
        :title="`What this run produced — from ${mainOutputPhase?.name ?? 'its last agent'}`"
        @click="showOutput = !showOutput"
      >
        <FileText :size="15" :stroke-width="2.2" />
        {{ showOutput ? 'hide output' : 'output' }}
      </button>
      <span class="run-stats">
        <StatChip kind="cost" :value="session.total_cost" />
        <StatChip kind="runtime" :value="sessionDurationMs" />
        <StatChip kind="tokens" :value="session.total_tokens" />
        <StatChip kind="read" :value="usage.read" />
        <StatChip kind="written" :value="usage.written" />
      </span>
    </div>

    <div v-if="showOutput && mainOutput" class="run-output">
      <div class="run-output-head">
        <span class="ro-title">run output</span>
        <button
          v-if="mainOutputPhase"
          type="button"
          class="ro-phase"
          title="Open the phase that produced this"
          @click="selectPhase(mainOutputPhase)"
        >
          {{ mainOutputPhase.name }}
        </button>
        <button class="ro-close" title="close" @click="showOutput = false">✕</button>
      </div>
      <EnvelopeOutput :envelope="mainOutput" />
    </div>

    <div class="phase-split" :class="{ 'has-detail': selectedPhase }" :style="{ '--phase-size': `${phaseListSize}px` }">
      <div id="phase-list-pane" class="phase-list-pane">
    <div v-if="phases.length" class="waterfall">
      <div class="row axis-row">
        <div class="label" />
        <div class="track">
          <span v-if="zonePct" class="zone-head" :style="{ width: `${zonePct}%` }">request</span>
          <span
            v-for="(t, i) in ticks"
            :key="i"
            class="axis-label"
            :class="{ edge: i === 0 }"
            :style="{ left: `${t.pct}%` }"
            >{{ t.label }}</span
          >
        </div>
      </div>

      <div v-for="lane in lanes" :key="lane.id" class="row lane" :class="`kind-${lane.kind}`">
        <div class="label">
          <span class="lane-name" :style="{ color: lane.color }" :title="lane.label">
            <component :is="KIND_ICONS[lane.kind]" class="lane-icon" :size="22" :stroke-width="2" />
            <span class="ellipsis">{{ lane.label }}</span>
          </span>
          <span v-if="lane.model" class="lane-meta lane-model" :title="lane.model">
            <img v-if="modelIcon(lane.model)" class="model-icon" :src="modelIcon(lane.model)!" alt="" />
            <span class="ellipsis">{{ modelName(lane.model) }}</span>
          </span>
          <span
            v-if="lane.context"
            class="lane-ctx"
            :title="`${NUM.format(lane.context.used)} / ${NUM.format(lane.context.window)} tokens used · ${NUM.format(lane.context.window - lane.context.used)} remaining`"
          >
            <span class="ctx-head">
              <span class="ctx-label">Context</span>
              <span class="ctx-pct">{{ contextLabel(lane.context) }}</span>
            </span>
            <span class="ctx-bar">
              <span
                class="ctx-fill"
                :style="{
                  width: contextFill(lane.context),
                  background: `linear-gradient(90deg, ${hexAlpha(lane.color, 0.55)}, ${lane.color})`,
                  boxShadow: `0 0 10px ${hexAlpha(lane.color, 0.45)}`,
                }"
              />
            </span>
          </span>
          <span v-for="(line, i) in lane.metaLines" :key="i" class="lane-meta">{{ line }}</span>
        </div>
        <div class="track">
          <span v-if="zonePct" class="zone-divider" :style="{ left: `${zonePct}%` }" />
          <span v-for="(t, i) in ticks" :key="i" class="gridline" :style="{ left: `${t.pct}%` }" />
          <template v-for="p in lane.phases" :key="p.phase_id">
            <button
              v-if="blockGeom(p)"
              class="block"
              :class="[p.status, { selected: p.phase_id === phaseId }]"
              :style="blockStyle(p, lane)"
              :title="`${p.name} — ${p.status}${p.description ? `\n${p.description}` : ''}`"
              @click="selectPhase(p)"
            >
              <span class="b-top">
                <span class="b-status" :class="p.status">{{
                  STATUS_GLYPH[p.status ?? ''] ?? '○'
                }}</span>
                <span class="b-name">{{ p.name }}</span>
                <StatChip
                  v-if="Number.isFinite(blockDurationMs(p))"
                  class="b-dur"
                  kind="runtime"
                  compact
                  :value="blockDurationMs(p)"
                />
              </span>
              <span class="b-desc">{{ p.description }}</span>
              <span v-if="ticksFor(p).length" class="tick-strip">
                <span
                  v-for="(tick, i) in ticksFor(p)"
                  :key="i"
                  class="tool-tick"
                  :class="{ err: !tick.ok }"
                  :style="{ left: `${tick.x}%` }"
                />
              </span>
            </button>
          </template>
          <button
            v-for="(p, i) in queuedByLane[lane.id]"
            :key="p.phase_id"
            class="block queued"
            :class="{ selected: p.phase_id === phaseId }"
            :style="{ right: `${10 + i * 5}px`, width: '170px' }"
            :title="`${p.name} — queued`"
            @click="selectPhase(p)"
          >
            <span class="b-top">
              <span class="b-status queued">○</span>
              <span class="b-name">{{ p.name }}</span>
            </span>
            <span class="b-desc">queued</span>
          </button>
        </div>
      </div>
    </div>
    <div v-else-if="loaded" class="empty-state">no phases recorded for this session</div>
    <div v-else-if="!apiError" class="empty-state">loading trace…</div>
      </div>
      <Splitter v-if="selectedPhase" storage-key="sssf:phase-size" label="Resize phase list" controls="phase-list-pane" :default-size="480" :min-size="160" :min-other="280" :narrow-at="1200" @resize="phaseListSize = $event" />
      <div v-if="selectedPhase" class="phase-detail-pane">
    <PhaseDetail
      :factory="factory"
      :phase="selectedPhase"
      :events="events"
      :envelopes="envelopes"
      :gates="gates"
      @close="navigate(props.factory, props.adwId)"
    />
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace { min-width: 0; }
.phase-split.has-detail { display: grid; grid-template-columns: minmax(0, var(--phase-size)) 8px minmax(0, 1fr); height: min(72vh, 900px); min-height: 320px; }
.phase-list-pane, .phase-detail-pane { min-width: 0; min-height: 0; overflow: auto; }
.phase-split.has-detail .waterfall { margin: 20px 12px; }
.phase-detail-pane :deep(.detail) { margin: 20px 12px; }
@media (max-width: 1200px) {
  .phase-split.has-detail { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, var(--phase-size)) 8px minmax(0, 1fr); height: min(75vh, 900px); }
}

.run-strip {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-soft);
  flex-wrap: wrap;
}

/* The run's result, one click from the run itself — the timeline is how the
   run got there, and that is a different question from what it produced. */
.output-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 13px;
  border: 1px solid rgba(200, 155, 255, 0.45);
  border-radius: 999px;
  background: rgba(200, 155, 255, 0.1);
  color: var(--text);
  font-family: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease;
}

.output-btn:hover,
.output-btn.on {
  border-color: rgba(200, 155, 255, 0.8);
  background: rgba(200, 155, 255, 0.18);
}

.run-output {
  margin: 18px 24px 0;
  padding: 14px 16px 16px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: var(--surface);
}

.run-output-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.ro-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: lowercase;
  color: var(--dim);
}

.ro-phase {
  padding: 2px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: transparent;
  color: var(--cyan);
  font-family: var(--mono);
  font-size: 15px;
  cursor: pointer;
}

.ro-phase:hover {
  border-color: rgba(148, 163, 255, 0.45);
}

.ro-close {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--dim);
  font-family: inherit;
  font-size: 17px;
  cursor: pointer;
}

.ro-close:hover {
  color: var(--text);
}

.run-strip .request {
  font-size: 17px;
  color: var(--text);
  max-width: 52ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-stats {
  display: inline-flex;
  gap: 12px;
  flex-wrap: wrap;
}

.waterfall {
  margin: 20px 28px;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
  /* The track needs real pixel width to stay readable — squeezing it to fit
     a phone screen is what truncated every block label to "Independe…". A
     narrow viewport scrolls the track horizontally instead; the label
     column stays put via `position: sticky` below. */
  overflow-x: auto;
  overflow-y: hidden;
}

.row {
  display: grid;
  grid-template-columns: 280px minmax(480px, 1fr);
  min-width: 760px;
}

.axis-row {
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}

.axis-row .label {
  background: var(--panel-2);
}

@media (max-width: 640px) {
  .row {
    grid-template-columns: 132px minmax(420px, 1fr);
    min-width: 552px;
  }
}

.axis-row .track {
  height: 40px;
  overflow: hidden;
}

.zone-head {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--amber);
  border-right: 1px solid var(--border);
}

.axis-label {
  position: absolute;
  bottom: 7px;
  transform: translateX(-50%);
  font-family: var(--mono);
  font-size: 16px;
  color: var(--dim);
  white-space: nowrap;
}

/* The first tick sits exactly on the request zone's edge, so centering it
   hangs half the label back over the "request" caption — they collided into
   "request0s" once the zone got narrow. It starts at the edge instead. */
.axis-label.edge {
  transform: none;
  padding-left: 3px;
}

.label {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  border-right: 1px solid var(--border);
  overflow: hidden;
  white-space: nowrap;
  /* Frozen first column: stays on screen while the track scrolls under/past
     it. Needs its own opaque background — sticky content isn't clipped by
     the row it sits in, so without one the scrolled-past track shows through. */
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--surface);
}

@media (max-width: 640px) {
  .label {
    padding: 8px 10px;
    gap: 0;
  }
  .lane-name {
    font-size: 14px;
    gap: 5px;
  }
  .lane-meta {
    font-size: 12px;
  }
  .lane-ctx {
    max-width: 110px;
  }
}

.lane-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lane-icon {
  flex: none;
  opacity: 0.85;
}

/* text-overflow needs a block box of its own: bare text beside the icon is an
   anonymous flex item, which ignores it and hard-cuts the name mid-letter. */
.ellipsis {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-meta {
  font-family: var(--mono);
  font-size: 16px;
  color: var(--dim);
  overflow: hidden;
  text-overflow: ellipsis;
}

.lane-model {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.model-icon {
  width: 17px;
  height: 17px;
  flex: none;
  object-fit: contain;
}

/* Context occupancy — label row over a thin track, under the model. */
.lane-ctx {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 2px;
  max-width: 190px;
}

.ctx-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.ctx-label {
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
}

.ctx-pct {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--dim);
}

.ctx-bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(6, 8, 15, 0.75);
  border: 1px solid var(--border-soft);
  overflow: hidden;
}

.ctx-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 300ms ease;
}

.lane {
  border-bottom: 1px solid var(--border-soft);
}

.lane:last-child {
  border-bottom: none;
}

.track {
  position: relative;
  height: 118px;
  overflow: hidden;
}

.zone-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px solid var(--border);
}

.gridline {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px dashed rgba(174, 191, 212, 0.14);
}

.block {
  position: absolute;
  top: 13px;
  height: 92px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 4px;
  padding: 10px 12px 16px;
  border-radius: 10px;
  border: 1px solid;
  font-size: 16px;
  color: var(--text);
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-align: left;
  transition: box-shadow 0.16s ease;
}

.block:hover {
  box-shadow: 0 0 18px var(--lane-glow, rgba(108, 182, 255, 0.2));
}

.b-top {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.b-status {
  flex: none;
  font-size: 16px;
}

.b-status.success {
  color: var(--green);
}

.b-status.fail {
  color: var(--red);
}

.b-status.running {
  color: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}

.b-status.queued {
  color: var(--faint);
}

.block .b-name {
  font-size: 17px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}

.block .b-dur {
  margin-left: auto;
  flex: none;
}

.block .b-desc {
  color: var(--dim);
  font-size: 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.block.running {
  animation: pulse 1.6s ease-in-out infinite;
}

.block.queued {
  background: transparent;
  border-style: dashed;
  border-color: var(--faint);
  color: var(--dim);
}

.block.selected {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
  box-shadow: 0 0 22px var(--lane-glow, rgba(108, 182, 255, 0.25));
}

/* The strip keeps the ticks inside the block's padding: 8px above the bottom
   border and 12px from the sides, so no tick can touch or cross the rounded
   corners no matter how wide or narrow the block is. */
.tick-strip {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 8px;
  height: 8px;
  pointer-events: none;
}

.tool-tick {
  position: absolute;
  bottom: 0;
  width: 3px;
  height: 8px;
  background: currentColor;
  opacity: 0.55;
  border-radius: 1px;
}

.tool-tick.err {
  background: var(--red);
  opacity: 1;
}
</style>
