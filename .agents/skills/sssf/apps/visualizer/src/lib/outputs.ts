/**
 * What a run or a phase actually produced, pulled out of its envelope.
 *
 * A model writes markdown — a Fusion plan, a panelist's proposal — and the
 * envelope carries it as one JSON string field. Splitting the prose out of
 * that payload is what lets it be rendered instead of shown with its own \n
 * escapes in it, and it happens in two places (a phase's outputs section and
 * the run-level output panel), so it lives here rather than in either.
 */
import { renderMarkdown } from './markdown'
import type { Envelope } from './types'

export interface ProseField {
  id: string
  key: string
  text: string
  html: string
  lines: number
}

/** Below this, a single-line string is a label, not something to render. */
const PROSE_MIN_CHARS = 180

/**
 * The string fields worth rendering, longest-lived first as the payload
 * declares them. Selection is by shape — multi-line, or long — so an output
 * type nobody here has heard of still renders its prose.
 */
export function proseFields(payloadJson: string | null | undefined, idPrefix: string): ProseField[] {
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(payloadJson ?? '{}') as Record<string, unknown>
  } catch {
    return [] // a malformed envelope still shows its raw JSON, never an error
  }
  const fields: ProseField[] = []
  for (const [key, value] of Object.entries(payload)) {
    if (typeof value !== 'string') continue
    if (!value.includes('\n') && value.length < PROSE_MIN_CHARS) continue
    fields.push({
      id: `${idPrefix}:${key}`,
      key,
      text: value,
      html: renderMarkdown(value),
      lines: value.split('\n').length,
    })
  }
  return fields
}

function planLength(envelope: Envelope): number {
  try {
    const payload = JSON.parse(envelope.payload_json ?? '{}') as Record<string, unknown>
    return typeof payload.plan === 'string' ? payload.plan.length : 0
  } catch {
    return 0
  }
}

/**
 * The one envelope a run is *about*, for the run-level output panel.
 *
 * A plan wins outright: in a Fusion run the votes come after the synthesis and
 * every one of them carries a summary long enough to look like prose, so
 * "whatever finished last" would hand back a ballot instead of the plan the
 * whole debate exists to produce. Failing a plan, the latest phase that wrote
 * any prose is the run's last word on itself.
 *
 * `seqOf` orders by the phase's own recorded seq rather than by envelope id or
 * arrival, because a parallel round finishes in whatever order it finishes.
 */
export function mainEnvelope(
  envelopes: Envelope[],
  seqOf: (phaseId: string | null) => number,
): Envelope | null {
  const ranked = envelopes
    .map((envelope) => ({ envelope, seq: seqOf(envelope.phase_id) }))
    .toSorted((a, b) => a.seq - b.seq)

  let plan: Envelope | null = null
  let prose: Envelope | null = null
  for (const { envelope } of ranked) {
    if (planLength(envelope) > 0) plan = envelope
    if (proseFields(envelope.payload_json, '').length) prose = envelope
  }
  return plan ?? prose ?? ranked.at(-1)?.envelope ?? null
}
