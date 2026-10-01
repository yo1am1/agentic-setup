import { expect, test } from 'bun:test'
import { mainEnvelope, proseFields } from './outputs'
import type { Envelope } from './types'

/** A stored envelope, with only the fields these two functions read. */
function envelope(phaseId: string, payload: Record<string, unknown>): Envelope {
  return {
    envelope_id: `env_${phaseId}`,
    adw_id: 'run',
    phase_id: phaseId,
    agent: 'agent',
    output_type: 'Output',
    payload_json: JSON.stringify(payload),
    valid: 1,
    attempt: 1,
    created_at: '2026-09-13T00:00:00Z',
  } as Envelope
}

/** Phase order as the trace recorded it — the seq, not arrival order. */
const SEQ: Record<string, number> = {
  opinion_1: 2,
  opinion_2: 3,
  synthesize_1: 8,
  vote_1: 9,
  vote_2: 10,
}
const seqOf = (id: string | null) => SEQ[id ?? ''] ?? -1

test('a long multi-line string is prose; a short label beside it is not', () => {
  const fields = proseFields(
    JSON.stringify({ status: 'success', plan: '# Plan\n\nDo the thing.', approved: true }),
    'env_1',
  )
  expect(fields.map((f) => f.key)).toEqual(['plan'])
  expect(fields[0]!.lines).toBe(3)
  expect(fields[0]!.html).toContain('<h1>Plan</h1>')
  expect(fields[0]!.id).toBe('env_1:plan')
})

test('a long single-line summary still counts as prose', () => {
  const long = 'x'.repeat(200)
  expect(proseFields(JSON.stringify({ summary: long }), 'e').map((f) => f.key)).toEqual(['summary'])
})

test('a malformed payload yields no prose rather than throwing', () => {
  expect(proseFields('{not json', 'e')).toEqual([])
  expect(proseFields(null, 'e')).toEqual([])
})

test('the run output is the plan, not the ballots cast after it', () => {
  // Every Fusion vote carries a summary long enough to read as prose, and the
  // votes are the LAST phases to finish — "whatever finished last" hands back
  // a ballot instead of the plan the whole debate exists to produce.
  const votes = 'Approved. '.repeat(30)
  const chosen = mainEnvelope(
    [
      envelope('opinion_1', { proposal: '## Position\n\nYes.' }),
      envelope('synthesize_1', { plan: '# Plan\n\nThe agreed plan.' }),
      envelope('vote_1', { summary: votes, approved: true }),
      envelope('vote_2', { summary: votes, approved: true }),
    ],
    seqOf,
  )
  expect(chosen?.phase_id).toBe('synthesize_1')
})

test('a later synthesis attempt supersedes an earlier one', () => {
  const chosen = mainEnvelope(
    [
      { ...envelope('opinion_1', { plan: 'first' }), phase_id: 'synthesize_1' },
      { ...envelope('vote_1', { plan: 'second' }), phase_id: 'vote_1' },
    ],
    (id) => (id === 'synthesize_1' ? 8 : 9),
  )
  expect(JSON.parse(chosen!.payload_json ?? '{}').plan).toBe('second')
})

test('with no plan anywhere, the latest phase that wrote prose is the run output', () => {
  const chosen = mainEnvelope(
    [
      envelope('opinion_1', { proposal: '# First\n\nprose' }),
      envelope('opinion_2', { proposal: '# Second\n\nprose' }),
      envelope('vote_1', { approved: true }),
    ],
    seqOf,
  )
  expect(chosen?.phase_id).toBe('opinion_2')
})

test('arrival order does not decide the winner — the phase seq does', () => {
  // A parallel round finishes in whatever order it finishes.
  const chosen = mainEnvelope(
    [
      envelope('vote_1', { summary: 'y'.repeat(200) }),
      envelope('synthesize_1', { plan: '# Plan' }),
      envelope('opinion_1', { proposal: 'p'.repeat(200) }),
    ],
    seqOf,
  )
  expect(chosen?.phase_id).toBe('synthesize_1')
})

test('an envelope with nothing worth rendering is still returned, so the panel shows its json', () => {
  const chosen = mainEnvelope([envelope('vote_1', { approved: true })], seqOf)
  expect(chosen?.phase_id).toBe('vote_1')
})

test('no envelopes at all means no run output panel', () => {
  expect(mainEnvelope([], seqOf)).toBeNull()
})
