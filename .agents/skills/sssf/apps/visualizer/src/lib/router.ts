import { ref } from 'vue'

// Hash routes, one segment per level of the breadcrumb:
//   #/                                → factories
//   #/<factory>                       → that factory's sessions
//   #/<factory>/<adw_id>              → waterfall
//   #/<factory>/<adw_id>/<phase_id>   → phase panel open
export interface Route {
  factory: string | null
  adwId: string | null
  phaseId: string | null
}

function parse(): Route {
  const parts = window.location.hash
    .replace(/^#\/?/, '')
    .split('/')
    .filter(Boolean)
    .map(decodeURIComponent)
  return { factory: parts[0] ?? null, adwId: parts[1] ?? null, phaseId: parts[2] ?? null }
}

const route = ref<Route>(parse())

window.addEventListener('hashchange', () => {
  route.value = parse()
})

export function useRoute() {
  return route
}

// Display name for the phase crumb — set by the trace view once phases load,
// since the phase_id in the URL is not the display name.
export const phaseCrumb = ref<string | null>(null)

// Each segment requires the one before it — there is no route to a session
// without the factory that owns it.
export function hrefFor(
  factory?: string | null,
  adwId?: string | null,
  phaseId?: string | null,
): string {
  let h = '#/'
  if (factory) h += encodeURIComponent(factory)
  if (factory && adwId) h += `/${encodeURIComponent(adwId)}`
  if (factory && adwId && phaseId) h += `/${encodeURIComponent(phaseId)}`
  return h
}

export function navigate(
  factory?: string | null,
  adwId?: string | null,
  phaseId?: string | null,
): void {
  window.location.hash = hrefFor(factory, adwId, phaseId)
}
