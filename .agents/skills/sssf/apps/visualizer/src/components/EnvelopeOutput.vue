<script setup lang="ts">
/**
 * One envelope, with the prose a model wrote rendered as the markdown it is.
 *
 * Used by a phase's outputs section and by the run-level output panel, which
 * is the point: the run panel is not a second, simpler rendering that drifts
 * from the real one — it is the same component on the run's headline envelope.
 */
import { computed, reactive, ref } from 'vue'
import { Braces } from 'lucide-vue-next'
import { proseFields } from '../lib/outputs'
import { highlightJsonPaths } from '../lib/highlight'
import type { Envelope } from '../lib/types'

const props = defineProps<{ envelope: Envelope }>()
const emit = defineEmits<{ path: [path: string] }>()

/** A path in the JSON is a button; the viewer that opens it belongs to the caller. */
function onJsonClick(event: MouseEvent) {
  const path = (event.target as HTMLElement).closest<HTMLElement>('button.j-path')?.dataset.path
  if (path) emit('path', path)
}

const prose = computed(() => proseFields(props.envelope.payload_json, props.envelope.envelope_id))

// Open on arrival — reading what was produced is the reason to be here — so
// this tracks what the reader has closed, the inverse of the prompt panels.
const closed = reactive(new Set<string>())
const raw = reactive(new Set<string>())
const jsonOpen = ref(false)

function toggle(id: string) {
  if (closed.has(id)) closed.delete(id)
  else closed.add(id)
}
</script>

<template>
  <div class="output">
    <div class="output-line">
      <span class="output-type">{{ envelope.output_type }}</span>
      <span class="tag">
        <span class="tag-k">agent</span>
        <span class="tag-v">{{ envelope.agent ?? '—' }}</span>
      </span>
      <span class="tag">
        <span class="tag-k">attempt</span>
        <span class="tag-v">{{ envelope.attempt ?? 0 }}</span>
      </span>
      <span class="output-valid" :class="envelope.valid ? 'pass' : 'fail'">
        {{ envelope.valid ? 'valid' : 'invalid' }}
      </span>
      <button v-if="prose.length" type="button" class="json-toggle" @click="jsonOpen = !jsonOpen">
        <Braces :size="14" :stroke-width="2" />
        {{ jsonOpen ? 'hide json' : 'envelope json' }}
      </button>
    </div>

    <div v-for="field in prose" :key="field.id" class="panel">
      <button class="panel-head" @click="toggle(field.id)">
        <span class="chev">{{ closed.has(field.id) ? '▸' : '▾' }}</span>
        <span class="panel-title">{{ field.key }}</span>
        <span class="dim">{{ field.lines }} lines</span>
      </button>
      <div v-if="!closed.has(field.id)" class="panel-body">
        <div class="panel-tools">
          <button :class="{ active: !raw.has(field.id) }" @click="raw.delete(field.id)">
            rendered
          </button>
          <button :class="{ active: raw.has(field.id) }" @click="raw.add(field.id)">raw</button>
        </div>
        <pre v-if="raw.has(field.id)" class="panel-raw">{{ field.text }}</pre>
        <!-- Safe: renderMarkdown escapes ALL input before emitting its own tags. -->
        <div v-else class="md" v-html="field.html" />
      </div>
    </div>

    <!-- Safe: highlightJsonPaths escapes ALL input before emitting its own
         spans and buttons; click is delegated since v-html content carries no
         Vue bindings of its own. -->
    <pre
      v-if="!prose.length || jsonOpen"
      class="json"
      v-html="highlightJsonPaths(envelope.payload_json)"
      @click="onJsonClick"
    />
  </div>
</template>

<style scoped>
.output {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.output-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 16px;
}

.output-type {
  font-family: var(--mono);
  font-weight: 700;
  color: var(--purple);
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  font-size: 15px;
}

.tag-k {
  color: var(--faint);
}

.tag-v {
  font-family: var(--mono);
}

.output-valid.pass {
  color: var(--green);
}

.output-valid.fail {
  color: var(--red);
}

.json-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 2px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: transparent;
  color: var(--dim);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
}

.json-toggle:hover {
  color: var(--text);
  border-color: rgba(148, 163, 255, 0.45);
}

.panel {
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  border: 0;
  background: var(--panel-2);
  color: var(--text);
  font-family: inherit;
  font-size: 16px;
  text-align: left;
  cursor: pointer;
}

.chev {
  color: var(--faint);
}

.panel-title {
  font-family: var(--mono);
  font-weight: 700;
}

.panel-head .dim {
  margin-left: auto;
  font-size: 15px;
}

/* No max-height: a plan is the thing this was opened to read, and a scrollbar
   inside a column inside a page is a bad way to read one. */
.panel-body {
  padding: 12px 14px 14px;
  border-top: 1px solid var(--border-soft);
}

.panel-tools {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.panel-tools button {
  padding: 2px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: transparent;
  color: var(--dim);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
}

.panel-tools button.active {
  color: var(--text);
  border-color: rgba(148, 163, 255, 0.45);
}

.panel-raw,
.json {
  margin: 0;
  font-family: var(--mono);
  font-size: 15px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
