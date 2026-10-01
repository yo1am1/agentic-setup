import type {
  LaunchRequest,
  OperatorOptions,
  WebRun,
  WebRunDetail,
  Envelope,
  EventRow,
  EventsPage,
  FactorySummary,
  FileView,
  GateResult,
  HealthResponse,
  PromptsResponse,
  SessionDetail,
  SessionSummary,
} from './types'

async function getJson(url: string): Promise<unknown> {
  const res = await fetch(url)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error ?? `GET ${url} → ${res.status}`)
  }
  return res.json()
}

let operatorToken = ''

export async function fetchOperator(): Promise<OperatorOptions> {
  const options = await getJson('/api/operator') as OperatorOptions
  operatorToken = options.token
  return options
}

async function postJson(url: string, body: unknown): Promise<unknown> {
  if (!operatorToken) await fetchOperator()
  const res = await fetch(url, { method: 'POST',
    headers: { 'content-type': 'application/json', 'x-sssf-token': operatorToken }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error ?? `POST ${url} → ${res.status}`)
  return data
}

/** The dsh web UI's current login link — a fresh token every time it's asked,
 * since dsh mints a new one whenever that service restarts. POST because the
 * server gates it behind the same operator token a write needs. */
export function fetchDshUrl(): Promise<{ url: string }> {
  return postJson('/api/dsh-url', {}) as Promise<{ url: string }>
}

export function launchWorkflow(factory: string, input: LaunchRequest): Promise<WebRun> {
  return postJson(`${base(factory)}/launch`, input) as Promise<WebRun>
}

export async function fetchWebRun(factory: string, id: string): Promise<WebRunDetail | null> {
  const res = await fetch(`${base(factory)}/launches/${encodeURIComponent(id)}`)
  if (res.status === 404) return null
  const data = await res.json()
  if (!res.ok) throw new Error(data.error ?? `launch status → ${res.status}`)
  return data
}

export function stopWebRun(factory: string, id: string): Promise<WebRunDetail> {
  return postJson(`${base(factory)}/launches/${encodeURIComponent(id)}/stop`, {}) as Promise<WebRunDetail>
}

/**
 * Every session request is scoped to the factory that owns it, mirroring the
 * hash route segment-for-segment. Relative paths throughout, so the built
 * bundle makes no assumption about which host or port serves it.
 */
function base(factory: string): string {
  return `/api/f/${encodeURIComponent(factory)}`
}

/** The factories index — the one route that is not scoped to a factory. */
export function fetchFactories(): Promise<FactorySummary[]> {
  return getJson('/api/factories') as Promise<FactorySummary[]>
}

export function fetchSessions(factory: string): Promise<SessionSummary[]> {
  return getJson(`${base(factory)}/sessions`) as Promise<SessionSummary[]>
}

export async function fetchSession(factory: string, adwId: string): Promise<SessionDetail> {
  const detail = (await getJson(
    `${base(factory)}/sessions/${encodeURIComponent(adwId)}`,
  )) as SessionDetail
  return {
    session: detail.session,
    usage: detail.usage ?? { read: 0, written: 0 },
    phases: detail.phases ?? [],
    agents: detail.agents ?? [],
  }
}

export async function fetchEvents(
  factory: string,
  adwId: string,
  after: number,
  limit = 500,
): Promise<EventsPage> {
  const page = (await getJson(
    `${base(factory)}/sessions/${encodeURIComponent(adwId)}/events?after=${after}&limit=${limit}`,
  )) as EventsPage | EventRow[]
  if (Array.isArray(page)) {
    const cursor = page.reduce((max, e) => Math.max(max, e.rowid), after)
    return { events: page, cursor, has_more: page.length === limit }
  }
  return { events: page.events ?? [], cursor: page.cursor ?? after, has_more: page.has_more ?? false }
}

/** Archive a run out of the review list (or restore it with archived=false). */
export async function archiveSession(
  factory: string,
  adwId: string,
  archived = true,
): Promise<void> {
  const url = `${base(factory)}/sessions/${encodeURIComponent(adwId)}/archive`
  await postJson(url, { archived })
}

/** Read a file, or list a directory, inside the factory repo a run worked in. */
export function fetchFile(factory: string, path: string): Promise<FileView> {
  return getJson(`${base(factory)}/files?path=${encodeURIComponent(path)}`) as Promise<FileView>
}

/** `refresh` names the one provider to read past the server's memo. */
export function fetchHealth(refresh?: 'codex' | 'claude' | 'agy'): Promise<HealthResponse> {
  return getJson(`/api/health${refresh ? `?refresh=${refresh}` : ''}`) as Promise<HealthResponse>
}

// PhaseDetail imports the prompts type from here alongside fetchPrompts.
export type { PromptsResponse }

export async function fetchPrompts(
  factory: string,
  adwId: string,
  agent: string,
): Promise<PromptsResponse> {
  const res = await fetch(
    `${base(factory)}/sessions/${encodeURIComponent(adwId)}/agents/${encodeURIComponent(agent)}/prompts`,
  )
  // Not recorded (or endpoint not deployed yet) renders as "no prompts", not an error.
  if (res.status === 404) return { system: null, user: null }
  if (!res.ok) throw new Error(`GET prompts → ${res.status}`)
  const data = (await res.json()) as Partial<PromptsResponse>
  return { system: data.system ?? null, user: data.user ?? null }
}

export function fetchEnvelopes(factory: string, adwId: string): Promise<Envelope[]> {
  return getJson(`${base(factory)}/sessions/${encodeURIComponent(adwId)}/envelopes`) as Promise<
    Envelope[]
  >
}

export function fetchGates(factory: string, adwId: string): Promise<GateResult[]> {
  return getJson(`${base(factory)}/sessions/${encodeURIComponent(adwId)}/gates`) as Promise<
    GateResult[]
  >
}
