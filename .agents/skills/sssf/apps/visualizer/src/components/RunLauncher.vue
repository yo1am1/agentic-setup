<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { OperatorOptions } from '../lib/types'
import { fetchOperator, launchWorkflow } from '../lib/api'
import { hrefFor, navigate } from '../lib/router'
import { FUSION_FLOWS, modelFamily } from '../../shared/fusion'

const props = defineProps<{ factory: string | null }>()
const OPEN_KEY = 'sssf.launcher.open'
const open = ref(localStorage.getItem(OPEN_KEY) === 'true')
const options = ref<OperatorOptions | null>(null)
const project = ref(props.factory ?? '')
const workflow = ref('scout')
const prompt = ref('')
const allowChanges = ref(false)
const busy = ref(false)
const error = ref('')
const selected = computed(() => options.value?.projects.find(value => value.name === project.value))
const flow = computed(() => selected.value?.workflows.find(value => value.id === workflow.value))
// The web launcher runs the roster's own panel; picking a different one is a
// terminal thing (--config on the CLI), so it is never asked here.
const roster = computed(() => selected.value?.configs[0])
const panel = ref('')
const needsModels = computed(() => FUSION_FLOWS.has(workflow.value))
const panelOptions = computed(() => roster.value?.panels ?? {})
const activePanel = computed(() => panel.value || roster.value?.selectedPanel || 'default')
const activePanelData = computed(() => activePanel.value === 'default' ? roster.value : panelOptions.value[activePanel.value])
const panelReady = computed(() => !needsModels.value || (activePanelData.value && !roster.value?.error && activePanelData.value.panel.length > 0))

/** The command that runs this exact request with full control, for the terminal. */
const cliHint = computed(() => {
  if (!flow.value) return ''
  const script = flow.value.script
  const base = `uv run adws/${script} "${prompt.value.trim() || '<request>'}"`
  return needsModels.value ? `${base} --models <model1> <model2> <model3>...` : base
})

async function refresh() {
  error.value = ''
  try {
    options.value = await fetchOperator()
    if (!selected.value) project.value = options.value.projects[0]?.name ?? ''
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
}

watch(() => props.factory, value => { if (value) project.value = value })
watch(selected, value => {
  if (!value?.workflows.some(item => item.id === workflow.value)) workflow.value = value?.workflows[0]?.id ?? ''
  panel.value = value?.configs[0]?.selectedPanel ?? ''
  allowChanges.value = false
})
watch(workflow, () => { allowChanges.value = false })
watch(open, value => localStorage.setItem(OPEN_KEY, String(value)))
onMounted(refresh)

async function start() {
  if (!flow.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    // No models/synthesizer: the ADW process reads the roster's own fusion:
    // panel itself. A custom panel for one run is a terminal thing.
    const run = await launchWorkflow(project.value, { runtime: 'pi', workflow: workflow.value,
      config: roster.value!.file, panel: panel.value || undefined,
      prompt: prompt.value, allow_changes: allowChanges.value })
    navigate(project.value, run.adw_id)
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
</script>

<template>
  <div class="dock" @keydown.esc="open = false">
    <section v-if="open" class="launcher" aria-labelledby="launch-title">
    <div class="launch-head">
      <h2 id="launch-title">Run a workflow</h2>
      <span class="head-actions">
        <button type="button" @click="refresh" :disabled="busy">Refresh</button>
        <button type="button" class="collapse" aria-label="Collapse launcher" @click="open = false">✕</button>
      </span>
    </div>
    <p class="dim">Use your local tools and credentials. Agent workflows may incur model costs.</p>
    <form @submit.prevent="start">
      <label>Project
        <select v-model="project" required :disabled="busy">
          <option value="" disabled>Select project</option>
          <option v-for="item in options?.projects" :key="item.name" :value="item.name">{{ item.name }}</option>
        </select>
      </label>
      <label>What do you want done?
        <select v-model="workflow" required :disabled="busy">
          <option v-for="item in selected?.workflows" :key="item.id" :value="item.id">{{ item.label }}</option>
        </select>
      </label>
      <p v-if="selected" class="project-path dim">{{ selected.path }}</p>
      <p v-if="selected?.error" role="alert">{{ selected.error }}</p>
      <label v-if="needsModels && roster && Object.keys(panelOptions).length">Fusion panel
        <select v-model="panel" :disabled="busy">
          <option value="">Default ({{ roster.selectedPanel }})</option>
          <option v-for="(_, name) in panelOptions" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <p v-if="needsModels && roster" class="panel-summary dim">
        <template v-if="!roster.error && activePanelData?.panel.length">
          Panel: {{ activePanelData.panel.map(m => modelFamily(m)).join(' → ') }}
          <span v-if="activePanelData.synthesizer"> · {{ modelFamily(activePanelData.synthesizer) }} collects</span>
        </template>
        <span v-else role="alert" class="warning">
          {{ roster.file }} has no usable Fusion panel — run this from the terminal instead.
        </span>
      </p>
      <label>Request
        <textarea v-model="prompt" rows="4" maxlength="32000" required :disabled="busy"
          placeholder="Describe the result you want, acceptance criteria, and what is out of scope." />
      </label>
      <label v-if="flow?.changes" class="confirmation">
        <input v-model="allowChanges" type="checkbox" required :disabled="busy" />
        I authorize changes in this project{{ flow.commits ? ', including Git commits. The working tree must be clean' : ' (plan files only)' }}.
      </label>
      <p v-if="options && !options.enabled" class="warning">Web launches currently require Linux. Observation remains available.</p>
      <p v-if="error" role="alert" class="error-bar">{{ error }}</p>
      <button class="start" type="submit" :disabled="busy || !options?.enabled || !flow || !panelReady">
        {{ busy ? 'Starting…' : 'Start workflow' }}
      </button>
      <details class="advanced">
        <summary>Full control (roster, panel, thinking level) — from the terminal</summary>
        <p class="dim">
          The web launcher always runs {{ roster?.file ?? "the project's roster" }} with its own configured
          settings. To pick a different roster, hand-pick or reorder a Fusion panel, or choose the synthesizer,
          run the same workflow from a terminal in the project — every flag is yours there.
        </p>
        <pre class="cli-hint">{{ cliHint }}</pre>
      </details>
    </form>
    <details v-if="selected?.web_runs.length" class="recent">
      <summary>Recent web launches (including startup failures)</summary>
      <ul>
        <li v-for="run in selected.web_runs" :key="run.adw_id">
          <a :href="hrefFor(project, run.adw_id)">{{ run.workflow }} · {{ run.adw_id }}</a> — {{ run.status }}
        </li>
      </ul>
    </details>
    </section>
    <button class="handle" type="button" :aria-expanded="open" @click="open = !open">
      {{ open ? 'Hide launcher' : 'Run a workflow' }}
    </button>
  </div>
</template>

<style scoped>
/* A dock, not a banner: the trace is the page, launching is an occasional act.
   Anchored bottom-right so it never pushes the runs below the fold. */
.dock { position: fixed; right: 20px; bottom: 20px; z-index: 30; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; max-width: calc(100vw - 40px); }
.handle { align-self: flex-end; padding: 10px 18px; border-radius: 999px; border-color: var(--cyan); background: var(--surface); box-shadow: 0 8px 24px rgba(0, 0, 0, .45); }
.launcher { width: min(440px, calc(100vw - 40px)); max-height: min(76vh, 760px); overflow-y: auto; padding: 18px; border: 1px solid var(--border-soft); border-radius: 14px; background: var(--surface); box-shadow: 0 18px 46px rgba(0, 0, 0, .55); }
.launch-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.head-actions { display: inline-flex; gap: 8px; }
.collapse { padding: 6px 10px; }
h2 { margin: 0; font-size: 20px; }
form, label { display: flex; flex-direction: column; gap: 9px; }
form { gap: 14px; }
select, textarea, button { font: inherit; color: var(--text); background: var(--bg); border: 1px solid var(--border-soft); border-radius: 8px; padding: 10px; }
select, textarea { width: 100%; min-width: 0; }
textarea { resize: vertical; }
select:focus-visible, textarea:focus-visible, button:focus-visible, input:focus-visible { outline: 2px solid var(--cyan); outline-offset: 3px; }
button { cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
.start { align-self: flex-start; border-color: var(--cyan); }
.confirmation { flex-direction: row; align-items: center; }
.project-path { overflow-wrap: anywhere; margin: 0; }
.panel-summary { margin: -4px 0 0; font-family: var(--mono); font-size: 13px; overflow-wrap: anywhere; }
.warning { color: var(--amber, #e8b64a); }
.advanced { margin-top: 2px; }
.advanced summary { cursor: pointer; font-size: 13px; color: var(--dim); }
.advanced p { margin: 8px 0; font-size: 13px; }
.cli-hint { margin: 0; padding: 8px 10px; border-radius: 8px; background: var(--bg); border: 1px solid var(--border-soft); font-family: var(--mono); font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
.recent { margin-top: 18px; }
.recent li { margin-top: 8px; }
</style>
