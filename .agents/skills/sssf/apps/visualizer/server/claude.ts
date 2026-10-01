/**
 * Claude Code subscription headroom from the same endpoint `/usage` reads.
 * This is a private CLI endpoint: fail closed if its response shape changes.
 * The public Agent SDK reports query cost, not subscription limits.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ClaudeUsage, CodexWindow } from "../shared/types.ts";

const USAGE_URL = "https://api.anthropic.com/api/oauth/usage";
// The access token in .credentials.json lasts 8h. Nothing refreshes it on this
// machine unless the CLI itself runs, so a dashboard left open outlives it and
// then sends an expired token — which answers 401, and enough 401s earn a 429
// that blanks the chip for an hour. Refreshing is what keeps that from being
// the steady state.
const TOKEN_URL = "https://console.anthropic.com/v1/oauth/token";
const OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
/** Refresh this long before the stated expiry, so a slow read can't straddle it. */
const REFRESH_SKEW_MS = 5 * 60_000;
const CREDENTIALS_FILE = join(
  process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), ".claude"),
  ".credentials.json",
);
const CACHE_MS = 5 * 60_000;
// 5s used to fail the cold-start read on every process boot: the very first
// request pays DNS + TLS handshake to a first-contact host, which alone can
// exceed 5s, while every later request reuses a warm connection and returns
// in well under a second. 10s covers the cold case without masking a truly
// dead endpoint.
const FETCH_TIMEOUT_MS = 10_000;

// `cached` throttles retries (a transient failure must not hammer the
// endpoint); `lastGood` survives a failed retry so one bad read doesn't blank
// the chip for a full CACHE_MS — it comes back marked source: "cached".
let cached: { at: number; usage: ClaudeUsage | null } | null = null;
let lastGood: ClaudeUsage | null = null;

// A 429 means the endpoint itself told us to back off — every retry against
// it, including a user's manual "refresh" click, only renews the block and
// never lets a quiet gap open up to succeed. Once set, no request goes out —
// force included — until this passes; only CACHE_MS-paced or user-triggered
// misses hit fetchLive() at all, so this is the one thing that must override
// `force` rather than just being bypassed by it.
let blockedUntil = 0;
const DEFAULT_RATE_LIMIT_BACKOFF_MS = 60_000;

interface RawWindow {
  utilization?: unknown;
  resets_at?: unknown;
}

function toWindow(label: string, seconds: number, raw: RawWindow | null): CodexWindow | null {
  if (
    !raw ||
    typeof raw.utilization !== "number" ||
    raw.utilization < 0 ||
    raw.utilization > 100
  ) return null;
  // A dormant window — no use since it last rolled over — reports
  // resets_at: null because nothing is scheduled. It still exists and still
  // has a quota, so keep it and let 0 mark "no reset scheduled yet".
  const parsed = typeof raw.resets_at === "string" ? Date.parse(raw.resets_at) : NaN;
  return {
    label,
    used_percent: raw.utilization,
    window_seconds: seconds,
    reset_at: Number.isFinite(parsed) ? Math.round(parsed / 1000) : 0,
  };
}

/** Kept separate from the network read so the external shape has one cheap check. */
export function parseClaudeUsage(
  raw: unknown,
  plan: string | null,
  asOf = new Date().toISOString(),
): ClaudeUsage | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as { five_hour?: RawWindow | null; seven_day?: RawWindow | null };
  const windows = [
    toWindow("5h", 18_000, body.five_hour ?? null),
    toWindow("weekly", 604_800, body.seven_day ?? null),
  ].filter((window): window is CodexWindow => window !== null);
  return windows.length
    ? { plan, windows, source: "live", as_of: asOf }
    : null;
}

function credentials(): {
  token: string;
  plan: string | null;
  refreshToken: string | null;
  expiresAt: number;
} | null {
  if (!existsSync(CREDENTIALS_FILE)) return null;
  try {
    const auth = JSON.parse(readFileSync(CREDENTIALS_FILE, "utf8")) as {
      claudeAiOauth?: {
        accessToken?: unknown;
        subscriptionType?: unknown;
        refreshToken?: unknown;
        expiresAt?: unknown;
      };
    };
    const oauth = auth.claudeAiOauth;
    if (typeof oauth?.accessToken !== "string") return null;
    return {
      token: oauth.accessToken,
      plan: typeof oauth.subscriptionType === "string" ? oauth.subscriptionType : null,
      refreshToken: typeof oauth.refreshToken === "string" ? oauth.refreshToken : null,
      expiresAt: typeof oauth.expiresAt === "number" ? oauth.expiresAt : 0,
    };
  } catch {
    return null;
  }
}

/**
 * Trade the refresh token for a fresh access token and write it back, so the
 * CLI and this dashboard keep sharing one valid credential.
 *
 * The write is read-modify-write on the whole document: `.credentials.json`
 * also holds `mcpOAuth`, which is none of this module's business and must
 * survive untouched. A refresh token may rotate, so whatever comes back is
 * persisted too — dropping it would strand the next refresh.
 */
async function refreshAccessToken(
  refreshToken: string,
): Promise<{ token: string; expiresAt: number } | null> {
  try {
    const response = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        grant_type: "refresh_token",
        refresh_token: refreshToken,
        client_id: OAUTH_CLIENT_ID,
      }),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      console.warn(`[claude usage] token refresh HTTP ${response.status}`);
      return null;
    }
    const body = (await response.json()) as {
      access_token?: unknown;
      refresh_token?: unknown;
      expires_in?: unknown;
    };
    if (typeof body.access_token !== "string") {
      console.warn("[claude usage] token refresh: no access_token in response");
      return null;
    }
    const expiresAt =
      Date.now() + (typeof body.expires_in === "number" ? body.expires_in : 8 * 3600) * 1000;

    try {
      const doc = JSON.parse(readFileSync(CREDENTIALS_FILE, "utf8")) as Record<string, unknown>;
      const oauth = (doc.claudeAiOauth ?? {}) as Record<string, unknown>;
      oauth.accessToken = body.access_token;
      oauth.expiresAt = expiresAt;
      if (typeof body.refresh_token === "string") oauth.refreshToken = body.refresh_token;
      doc.claudeAiOauth = oauth;
      writeFileSync(CREDENTIALS_FILE, JSON.stringify(doc, null, 2), { mode: 0o600 });
    } catch (error) {
      // A token we cannot persist is still a token we can use for this read.
      console.warn(`[claude usage] token refresh not persisted: ${(error as Error).message}`);
    }
    return { token: body.access_token, expiresAt };
  } catch (error) {
    console.warn(`[claude usage] token refresh failed: ${(error as Error).message}`);
    return null;
  }
}

/** Seconds (RFC 7231 delay-seconds) or absent — never the HTTP-date form here. */
function retryAfterMs(response: Response): number {
  const header = response.headers.get("retry-after");
  const seconds = header ? Number(header) : NaN;
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_RATE_LIMIT_BACKOFF_MS;
}

async function fetchLive(): Promise<ClaudeUsage | null> {
  const auth = credentials();
  if (!auth) return null;
  // Refresh *before* spending the request, not after a 401: a 401 is what
  // earns the hour-long 429, so the expired token must never leave here.
  let token = auth.token;
  if (auth.expiresAt && Date.now() > auth.expiresAt - REFRESH_SKEW_MS) {
    if (!auth.refreshToken) {
      console.warn("[claude usage] access token expired and no refresh token — run `claude` to re-auth");
      return null;
    }
    const refreshed = await refreshAccessToken(auth.refreshToken);
    if (!refreshed) return null;
    token = refreshed.token;
  }
  try {
    const response = await fetch(USAGE_URL, {
      headers: {
        authorization: `Bearer ${token}`,
        "anthropic-beta": "oauth-2025-04-20",
      },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (response.status === 429) {
      const waitMs = retryAfterMs(response);
      blockedUntil = Date.now() + waitMs;
      console.warn(`[claude usage] 429 rate limited — no reads for ${Math.round(waitMs / 1000)}s`);
      return null;
    }
    if (!response.ok) {
      console.warn(`[claude usage] HTTP ${response.status}`);
      return null;
    }
    const usage = parseClaudeUsage(await response.json(), auth.plan);
    if (!usage) console.warn("[claude usage] unrecognised response shape");
    return usage;
  } catch (error) {
    console.warn(`[claude usage] unreachable: ${(error as Error).message}`);
    return null;
  }
}

export async function readClaudeUsage(force = false): Promise<ClaudeUsage | null> {
  const withinCache = !force && cached && Date.now() - cached.at < CACHE_MS;
  const rateLimited = Date.now() < blockedUntil;
  if (withinCache || rateLimited) {
    return cached?.usage ?? (lastGood ? { ...lastGood, source: "cached" } : null);
  }
  const usage = await fetchLive();
  cached = { at: Date.now(), usage };
  if (usage) {
    lastGood = usage;
    return usage;
  }
  return lastGood ? { ...lastGood, source: "cached" } : null;
}
