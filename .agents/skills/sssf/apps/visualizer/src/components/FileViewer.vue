<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { File, Folder, X } from 'lucide-vue-next'
import type { FileView } from '../lib/types'
import { fetchFile } from '../lib/api'
import { highlightJsonPaths } from '../lib/highlight'
import { renderMarkdown } from '../lib/markdown'

const props = defineProps<{ factory: string; path: string }>()
const emit = defineEmits<{ close: []; navigate: [path: string] }>()

const view = ref<FileView | null>(null)
const error = ref('')
const loading = ref(false)
// A model's own output is what this viewer exists to read, not its raw
// encoding — a plan is a plan, not a wall of Markdown syntax. Reset with the
// path, not left at whatever the last file happened to be showing.
const raw = ref(false)

/** What a file's own extension says it should render as. Anything else stays
 * plain text — the pre-existing behavior for source code, logs, etc. */
const rendersAs = computed<'markdown' | 'json' | 'text'>(() => {
  const lower = props.path.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.markdown')) return 'markdown'
  if (lower.endsWith('.json')) return 'json'
  return 'text'
})

watch(
  () => [props.factory, props.path] as const,
  async ([factory, path]) => {
    loading.value = true
    error.value = ''
    raw.value = false
    try {
      view.value = await fetchFile(factory, path)
    } catch (e) {
      view.value = null
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

/** A .json file's own path-shaped fields (plan_path, report, …) stay
 * clickable here too — the same delegated-click trick PhaseDetail uses for
 * v-html content, but re-targeting this shared viewer via `navigate` rather
 * than a local ref, since this component does not own where it points. */
function onJsonClick(event: MouseEvent) {
  const path = (event.target as HTMLElement).closest<HTMLElement>('button.j-path')?.dataset.path
  if (path) emit('navigate', path)
}

/** Each crumb is the path up to and including that segment, so any level opens. */
function crumbs(path: string): { name: string; path: string }[] {
  const parts = path.split('/').filter(Boolean)
  return parts.map((name, index) => ({ name, path: parts.slice(0, index + 1).join('/') }))
}

function child(name: string): string {
  return props.path ? `${props.path}/${name}` : name
}

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <section class="viewer" aria-label="repository file viewer" @keydown.esc="emit('close')">
    <header>
      <nav class="crumbs">
        <button type="button" class="crumb" @click="emit('navigate', '')">{{ factory }}</button>
        <template v-for="crumb in crumbs(path)" :key="crumb.path">
          <span class="sep">/</span>
          <button type="button" class="crumb" @click="emit('navigate', crumb.path)">{{ crumb.name }}</button>
        </template>
      </nav>
      <button type="button" class="close" aria-label="Close file viewer" @click="emit('close')">
        <X :size="16" :stroke-width="2.4" />
      </button>
    </header>

    <p v-if="loading" class="faint pad">reading…</p>
    <p v-else-if="error" class="error pad" role="alert">{{ error }}</p>

    <ul v-else-if="view?.kind === 'dir'" class="entries">
      <li v-for="entry in view.entries" :key="entry.name">
        <button type="button" class="entry" @click="emit('navigate', child(entry.name))">
          <component :is="entry.kind === 'dir' ? Folder : File" :size="15" :stroke-width="2" />
          <span class="entry-name">{{ entry.name }}</span>
          <span v-if="entry.kind === 'file'" class="entry-size faint">{{ size(entry.size) }}</span>
        </button>
      </li>
      <li v-if="!view.entries.length" class="faint pad">empty directory</li>
    </ul>

    <template v-else-if="view?.kind === 'file'">
      <div v-if="rendersAs !== 'text'" class="view-tools">
        <button type="button" :class="{ active: !raw }" @click="raw = false">rendered</button>
        <button type="button" :class="{ active: raw }" @click="raw = true">raw</button>
      </div>
      <pre v-if="raw || rendersAs === 'text'" class="text">{{ view.text }}</pre>
      <!-- Safe: renderMarkdown/highlightJsonPaths escape ALL input before
           emitting their own tags; the JSON branch's click is delegated, the
           same reason PhaseDetail's own JSON dumps bind one click handler
           rather than per-token. -->
      <div v-else-if="rendersAs === 'markdown'" class="md pad file-md" v-html="renderMarkdown(view.text)" />
      <pre v-else class="text" v-html="highlightJsonPaths(view.text)" @click="onJsonClick" />
      <p v-if="view.truncated" class="faint pad">
        showing the first 512 KB of {{ size(view.bytes) }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.viewer {
  display: flex;
  flex-direction: column;
  max-height: 60vh;
  margin: 14px 0 4px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--bg);
  overflow: hidden;
}

header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}

.crumbs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
  font-family: var(--mono);
  font-size: 14px;
}

.crumb {
  padding: 2px 4px;
  border: 0;
  border-radius: 5px;
  background: none;
  color: var(--cyan);
  font: inherit;
  cursor: pointer;
}

.crumb:hover {
  background: rgba(90, 210, 221, 0.12);
}

.sep {
  color: var(--faint);
}

.close {
  margin-left: auto;
  display: inline-flex;
  padding: 4px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--dim);
  cursor: pointer;
}

.close:hover {
  color: var(--text);
}

.entries {
  margin: 0;
  padding: 6px;
  list-style: none;
  overflow: auto;
}

.entry {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.entry:hover {
  background: var(--panel-2);
}

.entry-name {
  overflow-wrap: anywhere;
}

.entry-size {
  margin-left: auto;
}

.text {
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1.55;
  white-space: pre;
  tab-size: 2;
}

.view-tools {
  display: flex;
  gap: 8px;
  padding: 8px 12px 0;
}

.view-tools button {
  padding: 2px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: none;
  color: var(--dim);
  font-family: var(--mono);
  font-size: 13px;
  cursor: pointer;
}

.view-tools button.active {
  color: var(--text);
  border-color: var(--border);
  background: var(--panel-2);
}

/* .md is a global class (style.css) shared with the compiled-prompt panel,
   which scrolls its own ancestor; this view scrolls itself instead, same as
   the plain-text branch beside it. */
.file-md {
  overflow: auto;
}

.pad {
  margin: 0;
  padding: 12px;
}

.error {
  color: var(--red);
}
</style>
