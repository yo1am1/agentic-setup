/**
 * Dependency-free JSON syntax highlighting.
 *
 * Same safety model as markdown.ts: every character of input is HTML-escaped;
 * the only tags in the output are the <span>s this module writes. Token
 * colors live in style.css under the .j-* classes.
 */

export function escapeHtml(s: string): string {
  return s
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

// Strings first so digits/keywords inside them are consumed as part of the
// string token. A string followed by a colon is an object key.
const TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false)\b|\b(null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g

/** Highlight text that is already (or claims to be) JSON. Escapes everything. */
export function highlightJsonText(text: string): string {
  let out = ''
  let last = 0
  for (const m of text.matchAll(TOKEN)) {
    out += escapeHtml(text.slice(last, m.index))
    const [full, str, colon, bool, nil, num] = m
    if (str !== undefined) {
      const cls = colon !== undefined ? 'j-key' : 'j-str'
      out += `<span class="${cls}">${escapeHtml(str)}</span>${escapeHtml(colon ?? '')}`
    } else if (bool !== undefined) {
      out += `<span class="j-bool">${bool}</span>`
    } else if (nil !== undefined) {
      out += `<span class="j-null">null</span>`
    } else {
      out += `<span class="j-num">${escapeHtml(num ?? full)}</span>`
    }
    last = (m.index ?? 0) + full.length
  }
  out += escapeHtml(text.slice(last))
  return out
}

/** Pretty-print raw JSON and highlight it; non-JSON falls back to escaped raw. */
export function highlightJson(raw: string | null | undefined): string {
  if (!raw) return ''
  try {
    return highlightJsonText(JSON.stringify(JSON.parse(raw), null, 2))
  } catch {
    return escapeHtml(raw)
  }
}

// ── Path-clickable JSON, for envelopes and phase logs ───────────────────────
// An envelope or a `ph.log()` names paths constantly — EnvelopeBase.artifacts,
// PlanOutput/DocumentOutput's *_path fields, ScoutFinding.file, and Fusion's
// own `plan`/`report` kwargs to ph.log() — but a name in a JSON dump is not
// the file. This turns the ones that are real paths into a button a caller
// can wire to the repo browser, without touching highlightJsonText/highlightJson
// (still used verbatim for tool-call args and prompt code fences).

/**
 * Field names this engine actually uses to carry a path. `plan` is
 * deliberately included and deliberately ambiguous — Fusion's own
 * FusionPlanOutput.plan is the markdown CONTENT, not a path, and only the
 * ph.log() at consensus time uses the same key for the path to it. The
 * value-shape check below is what tells those two apart; the key alone can't.
 */
const PATH_KEYS =
  /^(path|file|report|plan|artifacts|changed_files|documented_files|approved_plan)$|_path$|_file$/

/**
 * A string worth offering to open in the repo browser: short, single-line,
 * and shaped like a path rather than prose or a model id. Model ids
 * (`omniroute/codex/gpt-5.6-luna-medium`) contain slashes too, which is why
 * this is a second check, applied only to a PATH_KEYS field, not a filter run
 * over every string in the payload.
 */
function looksLikePath(value: string): boolean {
  if (!value || value.includes('\n') || value.length > 300) return false
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) return false // scheme:// — a URL, not a repo path
  return value.includes('/') || value.includes('\\') || /\.[A-Za-z0-9]{1,8}$/.test(value)
}

/**
 * Like highlightJson, but a string value under a path-shaped key becomes a
 * clickable `<button data-path="...">` — the caller wires one delegated click
 * handler to open it. Key tracking is a flat "last key seen" pass over the
 * token stream, not a real object walk: pretty-printed JSON always emits a
 * key immediately before its value, and that adjacency survives nesting well
 * enough here — an array of path strings under one key, or a path field
 * inside an array of objects, are both handled correctly; an unrelated
 * sibling key never inherits a pending one because every key token
 * overwrites it before its own value is checked.
 */
export function highlightJsonPaths(raw: string | null | undefined): string {
  if (!raw) return ''
  let pretty: string
  try {
    pretty = JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return escapeHtml(raw)
  }
  let out = ''
  let last = 0
  let pendingKey: string | null = null
  for (const m of pretty.matchAll(TOKEN)) {
    out += escapeHtml(pretty.slice(last, m.index))
    const [full, str, colon, bool, nil, num] = m
    if (str !== undefined) {
      // The literal, still-quoted token vs. its real content: e.g. an escaped
      // "\n" inside the quotes must decode to a real newline for the shape
      // check to see it and correctly refuse a multi-line value.
      let decoded = str
      try {
        decoded = JSON.parse(str) as string
      } catch {
        /* malformed escape in a hand-edited fixture; keep the quoted form */
      }
      if (colon !== undefined) {
        out += `<span class="j-key">${escapeHtml(str)}</span>${escapeHtml(colon)}`
        pendingKey = decoded
      } else if (pendingKey && PATH_KEYS.test(pendingKey) && looksLikePath(decoded)) {
        out += `<button type="button" class="j-path" data-path="${escapeHtml(decoded)}">${escapeHtml(str)}</button>`
      } else {
        out += `<span class="j-str">${escapeHtml(str)}</span>`
      }
    } else if (bool !== undefined) {
      out += `<span class="j-bool">${bool}</span>`
    } else if (nil !== undefined) {
      out += `<span class="j-null">null</span>`
    } else {
      out += `<span class="j-num">${escapeHtml(num ?? full)}</span>`
    }
    last = (m.index ?? 0) + full.length
  }
  out += escapeHtml(pretty.slice(last))
  return out
}
