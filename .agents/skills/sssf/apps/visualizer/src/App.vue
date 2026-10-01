<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, hrefFor, phaseCrumb } from './lib/router'
import type { AgyUsage, ClaudeUsage, CodexUsage } from './lib/types'
import { fetchDshUrl, fetchHealth, fetchOperator } from './lib/api'
import { ChevronDown, ExternalLink } from 'lucide-vue-next'
import CodexChip from './components/CodexChip.vue'
import FactoriesList from './components/FactoriesList.vue'
import Overview from './components/Overview.vue'
import SessionsList from './components/SessionsList.vue'
import Splitter from './components/Splitter.vue'
import SessionTrace from './components/SessionTrace.vue'
import RunLauncher from './components/RunLauncher.vue'

const route = useRoute()
const sessionsWidth = ref(310)
// Same host as this page, so the link works on localhost and over the tailnet alike.
const sslfUrl = `${location.protocol}//${location.hostname}:5173/`
const ssbfUrl = `${location.protocol}//${location.hostname}:4701/`
const ssttUrl = `${location.protocol}//${location.hostname}:4800/`

// Subscription quotas are deliberately NOT on the 500ms path the runs use:
// they move over hours, the server caches them for five minutes anyway, and
// polling faster would only add requests nobody reads.
const codex = ref<CodexUsage | null>(null)
const claude = ref<ClaudeUsage | null>(null)
const agy = ref<AgyUsage | null>(null)
const codexLoading = ref(true)
const claudeLoading = ref(true)
const agyLoading = ref(true)
const USAGE_POLL_MS = 5 * 60_000
let usageTimer: ReturnType<typeof setInterval> | undefined

// The live dot must mean it: a cheap health ping a few seconds apart decides
// whether the dot pulses green or holds red as "offline". The usage read above
// is far too slow a path to learn about a dead server from.
const apiUp = ref(true)
const HEALTH_PING_MS = 4_000
let healthTimer: ReturnType<typeof setInterval> | undefined
type ReplyNotification = { id: string; message: { senderName: string; text: string; source?: string; url?: string }; suggestions: string[] }
const replyNotification = ref<ReplyNotification | null>(null)
let lastReplyNotificationId: string | null = null
let notificationAudioContext: AudioContext | null = null
let replyTimer: ReturnType<typeof setInterval> | undefined

function audioContext() { return notificationAudioContext ??= new AudioContext() }
function playNotificationSound() {
  const context = audioContext()
  const oscillator = context.createOscillator()
  const gain = context.createGain()
  oscillator.frequency.value = 880
  gain.gain.setValueAtTime(0.12, context.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.25)
  oscillator.connect(gain).connect(context.destination)
  oscillator.start()
  oscillator.stop(context.currentTime + 0.25)
}

async function pullReplyNotification() {
  try {
    const response = await fetch('/api/reply-notifications')
    const data = await response.json()
    const next = data.notifications?.[0] ?? null
    if (next && next.id !== lastReplyNotificationId) {
      lastReplyNotificationId = next.id
      if (notificationAudioContext?.state === 'running') playNotificationSound()
    }
    replyNotification.value = next
  } catch {}
}

async function handleReply(action: 'approve' | 'dismiss', text?: string) {
  const item = replyNotification.value
  if (!item) return
  const { token } = await fetchOperator()
  const response = await fetch(`/api/reply-notifications/${item.id}/${action}`, {
    method: 'POST', headers: { 'content-type': 'application/json', 'x-sssf-token': token }, body: JSON.stringify(text ? { text } : {}),
  })
  if (!response.ok) return
  // Suggest-only sources (Google Chat, WhatsApp): copy the reply and open the chat.
  if (action === 'approve' && text && item.message.source && item.message.source !== 'telegram') {
    await navigator.clipboard?.writeText(text).catch(() => {})
    if (item.message.url) window.open(item.message.url, '_blank', 'noopener')
  }
  replyNotification.value = null
  await pullReplyNotification()
}

async function pingHealth() {
  try {
    await fetchHealth()
    apiUp.value = true
  } catch {
    apiUp.value = false
  }
}

// ── dsh link ─────────────────────────────────────────────────────────────────
// dsh mints a fresh login token every restart and needs it as a URL param on
// every fresh session — fetched fresh on each click rather than cached, since
// a token from an earlier click may already belong to a process that no
// longer exists. window.open happens synchronously inside the click handler
// wherever the await resolves fast enough for the browser not to treat it as
// an unrequested popup; the fallback link covers the rest.
const dshState = ref<'idle' | 'loading' | 'error'>('idle')
const dshFallback = ref<string | null>(null)

async function openDsh() {
  dshState.value = 'loading'
  dshFallback.value = null
  try {
    const { url } = await fetchDshUrl()
    dshState.value = 'idle'
    const opened = window.open(url, '_blank', 'noopener')
    if (!opened) dshFallback.value = url
  } catch {
    dshState.value = 'error'
  }
}

/** `provider` is a click on that one chip: only it reads upstream now, and only it spins. */
async function pullUsage(provider?: 'codex' | 'claude' | 'agy') {
  const flags = provider === 'codex' ? [codexLoading] : provider === 'claude' ? [claudeLoading] : provider === 'agy' ? [agyLoading] : [codexLoading, claudeLoading, agyLoading]
  if (provider && flags[0]!.value) return
  for (const flag of flags) flag.value = true
  try {
    const health = await fetchHealth(provider)
    codex.value = health.codex ?? null
    claude.value = health.claude ?? null
    agy.value = health.agy ?? null
    apiUp.value = true
  } catch {
    apiUp.value = false
  } finally {
    for (const flag of flags) flag.value = false
  }
}

onMounted(() => {
  window.addEventListener('pointerdown', () => void audioContext().resume(), { once: true })
  void pullUsage()
  void pingHealth()
  void pullReplyNotification()
  usageTimer = setInterval(() => void pullUsage(), USAGE_POLL_MS)
  healthTimer = setInterval(() => void pingHealth(), HEALTH_PING_MS)
  replyTimer = setInterval(() => void pullReplyNotification(), 10_000)
})

onUnmounted(() => {
  clearInterval(usageTimer)
  clearInterval(healthTimer)
  clearInterval(replyTimer)
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <nav class="crumbs">
        <!-- Ecosystem switch. The brand itself is the trigger: SSSF is this
             app, SSLF is a separate surface on its own port. Native <details>
             so there is no open/close state to own. -->
        <details class="eco">
          <summary>
            <!-- Inline copy of public/logo.svg (the favicon) so the mark
                 renders crisply with no fetch; keep the two in sync. -->
            <span class="eco-mark">
              <svg class="logo" viewBox="0 0 32 32" aria-hidden="true">
                <rect x="4" y="6" width="17" height="5" rx="2.5" fill="#e8b64a" />
                <rect x="8" y="13.5" width="20" height="5" rx="2.5" fill="#c89bff" />
                <rect x="4" y="21" width="13" height="5" rx="2.5" fill="#5ad2dd" />
              </svg>
            </span>
            <span class="brand">
              <small>Super Simple</small>
              <strong>Software Factory</strong>
            </span>
            <ChevronDown class="eco-caret" :size="15" :stroke-width="2.2" />
          </summary>
          <div class="eco-menu">
            <span class="eco-label">Ecosystem Factories</span>
            <a class="eco-item" :href="sslfUrl">
              <span class="eco-icon eco-icon--sslf">🌱</span>
              <span class="eco-item-body">
                <strong>SSLF · Life Factory</strong>
                <small>Main living, learning and planning space ↗</small>
              </span>
            </a>
            <span class="eco-item current">
              <span class="eco-icon eco-icon--sssf">
                <svg viewBox="0 0 32 32" aria-hidden="true">
                  <rect x="6" y="8" width="14" height="4" rx="2" fill="#e8b64a" />
                  <rect x="9" y="14" width="17" height="4" rx="2" fill="#c89bff" />
                  <rect x="6" y="20" width="11" height="4" rx="2" fill="#5ad2dd" />
                </svg>
              </span>
              <span class="eco-item-body">
                <strong>SSSF · Software Factory</strong>
                <small>Software, modules and agents (active)</small>
              </span>
              <em>✓</em>
            </span>
            <a class="eco-item" :href="ssbfUrl">
              <span class="eco-icon eco-icon--ssbf">
                <svg viewBox="0 0 32 32" aria-hidden="true">
                  <rect x="7" y="8" width="8" height="4" rx="2" fill="#c89bff" />
                  <rect x="17" y="8" width="8" height="4" rx="2" fill="#5ad2dd" />
                  <rect x="5" y="14" width="10" height="4" rx="2" fill="#c89bff" />
                  <rect x="17" y="14" width="10" height="4" rx="2" fill="#5ad2dd" />
                  <rect x="8" y="20" width="7" height="4" rx="2" fill="#c89bff" />
                  <rect x="17" y="20" width="7" height="4" rx="2" fill="#5ad2dd" />
                </svg>
              </span>
              <span class="eco-item-body">
                <strong>SSBF · Brain Factory</strong>
                <small>Agentic memory & LangGraph agents ↗</small>
              </span>
            </a>
            <a class="eco-item" :href="ssttUrl">
              <span class="eco-icon eco-icon--sstt">
                <svg viewBox="0 0 32 32" aria-hidden="true">
                  <rect x="5" y="7" width="22" height="4.5" rx="2.25" fill="#5ad2dd" />
                  <rect x="9" y="13.75" width="14" height="4.5" rx="2.25" fill="#c89bff" />
                  <rect x="6" y="20.5" width="20" height="4.5" rx="2.25" fill="#5ad2dd" />
                </svg>
              </span>
              <span class="eco-item-body">
                <strong>SSTT · Text Transcriber</strong>
                <small>Local meeting capture & transcription ↗</small>
              </span>
            </a>
          </div>
        </details>
        <span class="sep">›</span>
        <a :href="hrefFor()" :class="{ current: !route.factory }">factories</a>
        <template v-if="route.factory">
          <span class="sep">›</span>
          <a :href="hrefFor(route.factory)" :class="{ current: !route.adwId }">{{
            route.factory
          }}</a>
        </template>
        <template v-if="route.factory && route.adwId">
          <span class="sep">›</span>
          <a
            :href="hrefFor(route.factory, route.adwId)"
            :class="{ current: !route.phaseId }"
            >{{ route.adwId }}</a
          >
        </template>
        <template v-if="route.factory && route.adwId && route.phaseId">
          <span class="sep">›</span>
          <span class="current">{{ phaseCrumb ?? route.phaseId }}</span>
        </template>
      </nav>
      <span class="status">
        <!-- Rendered while the first read is still in flight too, so the chip
             appears with a spinner rather than popping in a second later. -->
        <!-- Always mounted, loading or not: a chip that vanishes on a failed
             read looks like nothing happened, when a quota fetch actually
             failed and needs a visible retry. -->
        <CodexChip :usage="codex" :loading="codexLoading" @refresh="pullUsage('codex')" />
        <CodexChip label="claude" :usage="claude" :loading="claudeLoading" @refresh="pullUsage('claude')" />
        <CodexChip label="agy" :usage="agy" :loading="agyLoading" @refresh="pullUsage('agy')" />
        <button
          type="button"
          class="dsh-link"
          :disabled="dshState === 'loading'"
          :title="dshState === 'error' ? 'could not reach dsh-web — is it running?' : 'open dsh, with a fresh login link'"
          @click="openDsh"
        >
          <ExternalLink :size="15" :stroke-width="2.2" />
          {{ dshState === 'loading' ? 'dsh…' : dshState === 'error' ? 'dsh failed' : 'dsh' }}
        </button>
        <span class="live-hint" :class="{ down: !apiUp }" :title="apiUp ? 'the server answers' : 'the server is not answering — check just go'">
          <span class="live-dot" /> {{ apiUp ? 'live' : 'offline' }}
        </span>
      </span>
      <!-- The browser blocked the popup (can happen after an async gap) —
           a real link the user clicks themselves opens with no such limit. -->
      <a
        v-if="dshFallback"
        class="dsh-fallback"
        :href="dshFallback"
        target="_blank"
        rel="noopener"
        @click="dshFallback = null"
        >dsh didn't open — click here</a
      >
    </header>
    <aside v-if="replyNotification" class="reply-notification" aria-live="polite">
      <button class="reply-close" aria-label="Dismiss" @click="handleReply('dismiss')">×</button>
      <strong>{{ replyNotification.message.senderName }}{{ replyNotification.message.source === 'gchat' ? ' · Google Chat' : '' }}</strong>
      <p>{{ replyNotification.message.text }}</p>
      <button v-for="text in replyNotification.suggestions" :key="text" @click="handleReply('approve', text)">{{ text }}</button>
    </aside>
    <main>
      <RunLauncher :factory="route.factory" />
      <template v-if="!route.factory">
        <Overview />
        <FactoriesList />
      </template>
      <div v-else-if="route.adwId" class="session-split" :style="{ '--sessions-size': `${sessionsWidth}px` }">
        <div id="sessions-pane" class="sessions-pane">
          <SessionsList :key="route.factory" :factory="route.factory" />
        </div>
        <Splitter storage-key="sssf:sessions-size" label="Resize sessions list" controls="sessions-pane" :default-size="310" :min-size="180" :min-other="360" @resize="sessionsWidth = $event" />
        <div class="trace-pane">
          <SessionTrace
            :key="`${route.factory}/${route.adwId}`"
            :factory="route.factory"
            :adw-id="route.adwId"
            :phase-id="route.phaseId"
          />
        </div>
      </div>
      <div v-else class="sessions-only"><SessionsList :key="route.factory" :factory="route.factory" /></div>
    </main>
  </div>
</template>

<style scoped>
.reply-notification{position:fixed;top:72px;right:24px;z-index:120;width:min(380px,calc(100vw - 32px));display:grid;gap:8px;padding:16px;background:#0d1119;border:1px solid #232c3d;border-radius:12px;box-shadow:0 16px 40px #0008}.reply-notification p{margin:0;color:#8b9cb6}.reply-notification>button:not(.reply-close){padding:8px 10px;text-align:left;color:#f2f5fa;background:#131a26;border:1px solid #232c3d;border-radius:8px}.reply-close{position:absolute;top:6px;right:8px;color:#8b9cb6;background:transparent;border:0;font-size:20px}

/* The launcher dock is fixed to the bottom-right corner. With nothing to
   scroll past it, it sat permanently on top of the last card's footer — room
   to scroll clear of it is the difference between a floating button and a
   button that eats content. */
main {
  padding-bottom: 88px;
}

.app { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
main { flex: 1; min-height: 0; overflow: auto; }
.session-split { height: 100%; min-height: 0; display: grid; grid-template-columns: var(--sessions-size) 8px minmax(0, 1fr); }
.sessions-pane, .trace-pane { min-width: 0; min-height: 0; overflow: auto; }
.sessions-only { height: 100%; overflow: auto; }
@media (max-width: 700px) {
  .session-split { grid-template-columns: minmax(0, 1fr); grid-template-rows: var(--sessions-size) 8px minmax(0, 1fr); }
}

.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: nowrap;
  gap: 12px;
  padding: 8px 28px;
  background: rgba(11, 15, 24, 0.72);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  position: sticky;
  top: 0;
  z-index: 10;
}

/* Gradient hairline instead of a hard border — the brand colors, whispered. */
.topbar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    rgba(200, 155, 255, 0.45),
    rgba(90, 210, 221, 0.35) 40%,
    rgba(90, 210, 221, 0.06)
  );
}

.crumbs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 17px;
  min-width: 0;
}

.logo {
  width: 21px;
  height: 21px;
  flex: none;
}

/* ── Ecosystem switch ─────────────────────────────────────────────────────── */
.eco {
  position: relative;
  min-width: 0;
}

.eco summary {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 6px 10px 6px 6px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
  list-style: none;
  transition: all 0.15s ease;
}

.eco summary::-webkit-details-marker {
  display: none;
}

.eco summary:hover,
.eco[open] summary {
  background: rgba(200, 155, 255, 0.08);
  border-color: rgba(200, 155, 255, 0.2);
}

.eco-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 10px;
  background: linear-gradient(140deg, rgba(200, 155, 255, 0.22), rgba(90, 210, 221, 0.18));
  box-shadow: inset 0 0 0 1px rgba(200, 155, 255, 0.25);
}

.brand {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  min-width: 0;
}

.brand small {
  color: var(--dim);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: 0.02em;
}

.brand strong {
  background: linear-gradient(90deg, var(--purple), var(--cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 700;
  font-size: 13px;
  line-height: 1.15;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.eco-caret {
  color: var(--faint);
  margin-left: 2px;
  flex: none;
  transition: transform 0.15s ease;
}

.eco[open] .eco-caret {
  transform: rotate(180deg);
}

.eco-menu {
  position: absolute;
  left: 0;
  top: calc(100% + 8px);
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 330px;
  padding: 8px;
  border-radius: 14px;
  background: rgba(14, 19, 30, 0.98);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55), inset 0 0 0 1px rgba(200, 155, 255, 0.14);
  z-index: 20;
}

.eco-label {
  margin: 5px 10px 8px;
  color: var(--faint);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* Same three-column grid the SSLF switcher uses — mark, text, tick — so the
   tick sits in its own track instead of being pushed around by the title's
   length, and every row lands on the same baseline. */
.eco-item {
  display: grid;
  grid-template-columns: 30px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 9px;
  color: var(--text);
  transition: background 0.12s ease;
}

.eco-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 16px;
}

.eco-icon--sslf {
  background: #1b4332;
}

.eco-icon--sssf,
.eco-icon--ssbf,
.eco-icon--sstt {
  background: #11161f;
}

.eco-icon svg {
  width: 20px;
  height: 20px;
}

.eco-item-body {
  min-width: 0;
}

.eco-item strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
}

.eco-item small {
  display: block;
  margin-top: 2px;
  color: var(--dim);
  font-size: 11px;
}

.eco-item em {
  color: var(--cyan);
  font-style: normal;
}

a.eco-item:hover {
  background: rgba(200, 155, 255, 0.12);
}

.eco-item.current {
  background: rgba(90, 210, 221, 0.1);
}

/* Keeps the chip and the live hint on one baseline at the right of the bar,
   so adding the chip does not move the crumbs. */
.status {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  flex: none;
  max-width: 100%;
  min-width: 0;
}

.dsh-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: rgba(19, 26, 38, 0.6);
  color: var(--dim);
  font-family: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    color 0.18s ease;
}

.dsh-link:hover:not(:disabled) {
  border-color: rgba(148, 163, 255, 0.45);
  color: var(--text);
}

.dsh-link:disabled {
  cursor: progress;
  opacity: 0.7;
}

.dsh-fallback {
  flex: 0 0 100%;
  color: var(--cyan);
  font-size: 15px;
  text-decoration: underline;
}

.live-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--dim);
  font-size: 16px;
  white-space: nowrap;
}

.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 10px rgba(74, 222, 128, 0.7);
  animation: pulse 1.6s ease-in-out infinite;
}

/* A dead server must not get a healthy pulse: hold red and stand still. */
.live-hint.down {
  color: var(--red);
}

.live-hint.down .live-dot {
  background: var(--red);
  box-shadow: 0 0 10px rgba(255, 111, 103, 0.7);
  animation: none;
}

@media (max-width: 700px) {
  .topbar {
    padding-inline: 14px;
    justify-content: flex-start;
    gap: 8px;
  }

  .crumbs {
    flex: none;
    flex-wrap: nowrap;
  }

  .crumbs > :not(.eco) {
    display: none;
  }

  .brand {
    display: none;
  }

  .status {
    flex: 1 1 auto;
    flex-wrap: nowrap;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .status::-webkit-scrollbar {
    display: none;
  }

  .status > * {
    flex: none;
  }
}
</style>
