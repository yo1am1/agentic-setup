import { expect, test } from 'bun:test'
import { highlightJson, highlightJsonPaths } from './highlight'

/** Pull `data-path` values out of the rendered HTML, in document order. */
function clickablePaths(html: string): string[] {
  return [...html.matchAll(/data-path="([^"]*)"/g)].map((m) => m[1]!)
}

test('a real path under a real path-shaped key becomes clickable, exactly once', () => {
  const envelope = JSON.stringify({
    status: 'success',
    plan_path: 'adws/adw_data/sessions/f5ebae05/context_handoff/fusion_92b82423/plan_1.md',
  })
  const html = highlightJsonPaths(envelope)
  expect(clickablePaths(html)).toEqual([
    'adws/adw_data/sessions/f5ebae05/context_handoff/fusion_92b82423/plan_1.md',
  ])
  // The escaped, still-clickable text is what a reader sees; the raw path
  // must not leak past HTML escaping into the element content.
  expect(html).toContain('adws/adw_data/sessions/f5ebae05/context_handoff/fusion_92b82423/plan_1.md')
})

test('an array of paths under one key are all clickable, not just the first', () => {
  const html = highlightJsonPaths(JSON.stringify({ artifacts: ['a/one.md', 'a/two.json'] }))
  expect(clickablePaths(html)).toEqual(['a/one.md', 'a/two.json'])
})

test('a path field nested inside an array of objects is still found', () => {
  // ScoutOutput.findings: [{file, note}] — the key that matters is one level
  // deep, and a sibling "note" string must not inherit it.
  const html = highlightJsonPaths(
    JSON.stringify({ findings: [{ file: 'src/app.py', note: 'this is where auth lives' }] }),
  )
  expect(clickablePaths(html)).toEqual(['src/app.py'])
  expect(html).not.toContain('data-path="this is where auth lives"')
})

test('a model id is not a path, even though it has slashes', () => {
  // The exact shape a real consensus report carries: {"models": {seat: modelId}}.
  // Neither "models" nor a per-seat key is in the path whitelist.
  const html = highlightJsonPaths(
    JSON.stringify({ models: { fusion_1_abc: 'omniroute/codex/gpt-5.6-luna-medium' } }),
  )
  expect(clickablePaths(html)).toEqual([])
})

test('FusionPlanOutput.plan is markdown content, not a path, despite the key name', () => {
  // `plan` is deliberately in the whitelist (Fusion's own ph.log() reuses it
  // for a path) — this is what tells the two apart: the shape, not the key.
  const html = highlightJsonPaths(
    JSON.stringify({ status: 'success', plan: '# Plan\nDo the smallest thing.\nRisk: none.' }),
  )
  expect(clickablePaths(html)).toEqual([])
  expect(html).toContain('j-str')
})

test('the same key, used for a real path elsewhere, is clickable', () => {
  // The consensus phase's own ph.log(plan=str(plan_path)) call: same "plan"
  // key, a short single-line path this time.
  const html = highlightJsonPaths(JSON.stringify({ consensus: true, plan: 'a/plan_1.md' }))
  expect(clickablePaths(html)).toEqual(['a/plan_1.md'])
})

test('a URL is a path-shaped key but not a repo path', () => {
  const html = highlightJsonPaths(JSON.stringify({ path: 'https://example.com/a/b' }))
  expect(clickablePaths(html)).toEqual([])
})

test('a plain filename with no slash still counts, by its extension', () => {
  const html = highlightJsonPaths(JSON.stringify({ report: 'consensus_1.json' }))
  expect(clickablePaths(html)).toEqual(['consensus_1.json'])
})

test('a path value is HTML-escaped in the data-path attribute', () => {
  const html = highlightJsonPaths(JSON.stringify({ path: 'a/"b"<c>.md' }))
  expect(html).toContain('data-path="a/&quot;b&quot;&lt;c&gt;.md"')
  expect(html).not.toContain('data-path="a/"b"<c>.md"')
})

test('malformed JSON falls back to escaped raw text, like highlightJson', () => {
  const broken = '{not json'
  expect(highlightJsonPaths(broken)).toBe(highlightJson(broken))
})

test('empty and nullish input render as nothing, like highlightJson', () => {
  expect(highlightJsonPaths('')).toBe('')
  expect(highlightJsonPaths(null)).toBe('')
  expect(highlightJsonPaths(undefined)).toBe('')
})
