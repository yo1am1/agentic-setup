/**
 * How much of the Codex subscription is left.
 *
 * Every agent in every factory bills against one weekly quota, and nothing in
 * the trace shows it — the first sign of exhaustion is a chain dying mid-run.
 * This is the number that prevents that surprise.
 *
 * Two sources, in order:
 *
 *   live    `chatgpt.com/backend-api/wham/usage` with the token the Codex CLI
 *           already holds. It is a metadata read, not a model call — repeated
 *           requests leave used_percent untouched — so polling it is free and
 *           the figure is never stale.
 *   cached  the snapshot the CLI writes into its session rollouts. No token, no
 *           network, but only as fresh as the last time `codex` itself ran,
 *           which is not when a FACTORY runs: pi does not record rate limits.
 *
 * The live answer is memoised so a dashboard full of tabs cannot turn a 500ms
 * UI poll into 500ms upstream requests.
 *
 * NOTHING identifying leaves this module. The upstream response carries an
 * email and account ids alongside the quota; only the quota is returned.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { CodexUsage, CodexWindow } from "../shared/types.ts";

const USAGE_URL = "https://chatgpt.com/backend-api/wham/usage";
const CODEX_HOME = join(homedir(), ".codex");
const AUTH_FILE = join(CODEX_HOME, "auth.json");
const SESSIONS_DIR = join(CODEX_HOME, "sessions");

/** Upstream is polled at most this often, however many clients are watching. */
const CACHE_MS = 5 * 60_000;
/** A quota check must never be why a page hangs. */
const FETCH_TIMEOUT_MS = 5_000;
/** Newest rollouts to search for the fallback snapshot before giving up. */
const ROLLOUTS_SCANNED = 40;

let cached: { at: number; usage: CodexUsage | null } | null = null;

/** "weekly" reads better than "604800s", and the caller should not do maths. */
function windowLabel(seconds: number): string {
  if (seconds % 604_800 === 0) {
    const weeks = seconds / 604_800;
    return weeks === 1 ? "weekly" : `${weeks}w`;
  }
  if (seconds % 86_400 === 0) {
    const days = seconds / 86_400;
    return days === 1 ? "daily" : `${days}d`;
  }
  if (seconds % 3_600 === 0) return `${seconds / 3_600}h`;
  return `${Math.round(seconds / 60)}m`;
}

/**
 * The access token the Codex CLI stores after `codex login`.
 *
 * Searched for by name rather than by a fixed path into the file: this is
 * somebody else's on-disk format, and a rename one level down should degrade to
 * the cached snapshot rather than throw.
 */
function findAccessToken(node: unknown): string | null {
  if (!node || typeof node !== "object") return null;
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    if ((key === "access_token" || key === "access") && typeof value === "string") return value;
    const nested = findAccessToken(value);
    if (nested) return nested;
  }
  return null;
}

function accessToken(): string | null {
  if (!existsSync(AUTH_FILE)) return null;
  try {
    return findAccessToken(JSON.parse(readFileSync(AUTH_FILE, "utf8")));
  } catch {
    return null;
  }
}

interface UpstreamWindow {
  used_percent?: number;
  limit_window_seconds?: number;
  reset_at?: number;
}

function toWindow(raw: UpstreamWindow | null | undefined): CodexWindow | null {
  if (!raw || typeof raw.used_percent !== "number") return null;
  const seconds = raw.limit_window_seconds ?? 0;
  return {
    label: windowLabel(seconds),
    used_percent: raw.used_percent,
    window_seconds: seconds,
    reset_at: raw.reset_at ?? 0,
  };
}

async function fetchLive(): Promise<CodexUsage | null> {
  const token = accessToken();
  if (!token) return null;
  try {
    const response = await fetch(USAGE_URL, {
      headers: { authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!response.ok) return null;      // 401 once the token expires — fall back
    const body = (await response.json()) as {
      plan_type?: string;
      rate_limit?: { primary_window?: UpstreamWindow; secondary_window?: UpstreamWindow };
    };
    // Only these fields are read. The rest of the payload identifies the
    // account and is deliberately left behind.
    const windows = [
      toWindow(body.rate_limit?.primary_window),
      toWindow(body.rate_limit?.secondary_window),
    ].filter((w): w is CodexWindow => w !== null);
    if (!windows.length) return null;
    return {
      plan: body.plan_type ?? null,
      windows,
      source: "live",
      as_of: new Date().toISOString(),
    };
  } catch {
    return null;                        // offline, DNS, timeout — all the same here
  }
}

/**
 * The newest rate-limit record the Codex CLI left on disk.
 *
 * Rollouts are append-only, so the record is near the end; scanning the newest
 * files backwards and stopping at the first hit keeps this at a fraction of a
 * second even across a few hundred megabytes of sessions.
 */
function readCached(): CodexUsage | null {
  if (!existsSync(SESSIONS_DIR)) return null;
  let files: { path: string; mtime: number }[] = [];
  const walk = (dir: string, depth: number): void => {
    if (depth > 3) return;
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      const path = join(dir, entry);
      try {
        const stat = statSync(path);
        if (stat.isDirectory()) walk(path, depth + 1);
        else if (entry.startsWith("rollout-") && entry.endsWith(".jsonl")) {
          files.push({ path, mtime: stat.mtimeMs });
        }
      } catch {
        /* vanished between listing and stat */
      }
    }
  };
  walk(SESSIONS_DIR, 0);

  files = files.toSorted((a, b) => b.mtime - a.mtime).slice(0, ROLLOUTS_SCANNED);
  for (const file of files) {
    let lines: string[];
    try {
      lines = readFileSync(file.path, "utf8").split("\n");
    } catch {
      continue;
    }
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (!line || !line.includes('"rate_limits"')) continue;
      try {
        const record = JSON.parse(line) as {
          timestamp?: string;
          payload?: {
            rate_limits?: {
              plan_type?: string;
              primary?: { used_percent?: number; window_minutes?: number; resets_at?: number };
              secondary?: { used_percent?: number; window_minutes?: number; resets_at?: number };
            };
          };
        };
        const limits = record.payload?.rate_limits;
        if (!limits) continue;
        // The on-disk shape counts in MINUTES where the endpoint counts in
        // seconds, and names the fields differently. Normalised here so callers
        // never learn which source they got.
        const windows = [limits.primary, limits.secondary]
          .map((w) =>
            toWindow(
              w
                ? {
                    used_percent: w.used_percent,
                    limit_window_seconds: (w.window_minutes ?? 0) * 60,
                    reset_at: w.resets_at,
                  }
                : null,
            ),
          )
          .filter((w): w is CodexWindow => w !== null);
        if (!windows.length) continue;
        return {
          plan: limits.plan_type ?? null,
          windows,
          source: "cached",
          as_of: record.timestamp ?? new Date(file.mtime).toISOString(),
        };
      } catch {
        /* a truncated final line is normal on a session still being written */
      }
    }
  }
  return null;
}

/**
 * Live if it answers, else the last snapshot on disk, else nothing.
 *
 * `force` skips the memo for an explicit refresh — someone clicking the chip is
 * asking about right now, and making them wait out a five minute window would
 * answer a question they did not ask. The result still refreshes the memo, so a
 * click also serves every other tab.
 */
export async function readCodexUsage(force = false): Promise<CodexUsage | null> {
  if (!force && cached && Date.now() - cached.at < CACHE_MS) return cached.usage;
  const usage = (await fetchLive()) ?? readCached();
  cached = { at: Date.now(), usage };
  return usage;
}
