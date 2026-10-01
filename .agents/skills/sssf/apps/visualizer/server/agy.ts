/**
 * Antigravity (agy) CLI subscription headroom from retrieveUserQuotaSummary.
 */
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { CodexUsage, CodexWindow } from "../shared/types.ts";

const USAGE_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary";
const AUTH_FILE = join(homedir(), ".gemini", "antigravity-cli", "antigravity-oauth-token");
const USER_AGENT = "antigravity/cli/1.1.5 (aidev_client; os_type=darwin; arch=arm64; auth_method=consumer)";
const CACHE_MS = 5 * 60_000;
const FETCH_TIMEOUT_MS = 10_000;

let cached: { at: number; usage: CodexUsage | null } | null = null;
let lastGood: CodexUsage | null = null;
let blockedUntil = 0;
const DEFAULT_RATE_LIMIT_BACKOFF_MS = 60_000;

interface RawBucket {
  window?: unknown;
  remainingFraction?: unknown;
  resetTime?: unknown;
}

interface RawGroup {
  displayName?: unknown;
  buckets?: RawBucket[] | null;
}

interface RawQuotaSummary {
  groups?: RawGroup[] | null;
  buckets?: RawBucket[] | null;
  models?: Record<string, { quotaInfo?: { remainingFraction?: unknown; resetTime?: unknown } | null }> | null;
}

function toWindow(raw: RawBucket | null | undefined, groupName?: string): CodexWindow | null {
  if (!raw || typeof raw.remainingFraction !== "number") return null;
  if (raw.remainingFraction < 0 || raw.remainingFraction > 1) return null;

  const used_percent = Math.round((1 - raw.remainingFraction) * 100);
  const parsed = typeof raw.resetTime === "string" ? Date.parse(raw.resetTime) : NaN;
  const reset_at = Number.isFinite(parsed) ? Math.round(parsed / 1000) : 0;
  const label = raw.window === "weekly" ? "weekly" : "5h";
  const window_seconds = label === "weekly" ? 604_800 : 18_000;

  return {
    label,
    used_percent,
    window_seconds,
    reset_at,
    ...(groupName ? { group: groupName } : {}),
  };
}

export function parseAgyUsage(
  raw: unknown,
  plan: string | null = "Antigravity",
  asOf = new Date().toISOString(),
): CodexUsage | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as RawQuotaSummary;

  const windows: CodexWindow[] = [];
  const seen = new Set<string>();

  if (Array.isArray(body.groups) && body.groups.length > 0) {
    for (const group of body.groups) {
      const groupName = typeof group?.displayName === "string" ? group.displayName : undefined;
      if (Array.isArray(group?.buckets)) {
        for (const bucket of group.buckets) {
          const w = toWindow(bucket, groupName);
          const key = `${groupName ?? ""}:${w?.label}`;
          if (w && !seen.has(key)) {
            seen.add(key);
            windows.push(w);
          }
        }
      }
    }
  } else if (Array.isArray(body.buckets)) {
    for (const bucket of body.buckets) {
      const w = toWindow(bucket);
      if (w && !seen.has(w.label)) {
        seen.add(w.label);
        windows.push(w);
      }
    }
  }

  // Fallback: models map with quotaInfo (if passed fetchAvailableModels format)
  if (!windows.length && body.models && typeof body.models === "object") {
    for (const model of Object.values(body.models)) {
      const qi = model?.quotaInfo;
      const w = toWindow({
        window: "5h",
        remainingFraction: qi?.remainingFraction,
        resetTime: qi?.resetTime,
      });
      if (w) {
        windows.push(w);
        break;
      }
    }
  }

  return windows.length
    ? { plan, windows, source: "live", as_of: asOf }
    : null;
}

function credentials(): { token: string; plan: string | null } | null {
  if (!existsSync(AUTH_FILE)) return null;
  try {
    const auth = JSON.parse(readFileSync(AUTH_FILE, "utf8")) as {
      token?: { access_token?: unknown };
      access_token?: unknown;
    };
    const token =
      typeof auth.token?.access_token === "string"
        ? auth.token.access_token
        : typeof auth.access_token === "string"
          ? auth.access_token
          : null;
    if (!token) return null;
    return { token, plan: "Antigravity" };
  } catch {
    return null;
  }
}

function retryAfterMs(response: Response): number {
  const header = response.headers.get("retry-after");
  const seconds = header ? Number(header) : NaN;
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_RATE_LIMIT_BACKOFF_MS;
}

async function fetchLive(): Promise<CodexUsage | null> {
  const auth = credentials();
  if (!auth) return null;
  try {
    const response = await fetch(USAGE_URL, {
      method: "POST",
      headers: {
        authorization: `Bearer ${auth.token}`,
        "content-type": "application/json",
        "user-agent": USER_AGENT,
      },
      body: "{}",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (response.status === 429) {
      const waitMs = retryAfterMs(response);
      blockedUntil = Date.now() + waitMs;
      console.warn(`[agy usage] 429 rate limited — no reads for ${Math.round(waitMs / 1000)}s`);
      return null;
    }
    if (!response.ok) {
      console.warn(`[agy usage] HTTP ${response.status}`);
      return null;
    }
    const usage = parseAgyUsage(await response.json(), auth.plan);
    if (!usage) console.warn("[agy usage] unrecognised response shape");
    return usage;
  } catch (error) {
    console.warn(`[agy usage] unreachable: ${(error as Error).message}`);
    return null;
  }
}

export async function readAgyUsage(force = false): Promise<CodexUsage | null> {
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
