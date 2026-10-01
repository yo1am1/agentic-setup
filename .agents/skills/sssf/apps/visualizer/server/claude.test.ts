import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseClaudeUsage } from "./claude.ts";

test("normalizes Claude's five-hour and weekly usage", () => {
  const usage = parseClaudeUsage(
    {
      five_hour: { utilization: 12.5, resets_at: "2026-08-12T12:00:00Z" },
      seven_day: { utilization: 34, resets_at: "2026-08-17T12:00:00Z" },
    },
    "pro",
    "2026-08-12T10:00:00Z",
  );

  expect(usage).toEqual({
    plan: "pro",
    source: "live",
    as_of: "2026-08-12T10:00:00Z",
    windows: [
      { label: "5h", used_percent: 12.5, window_seconds: 18_000, reset_at: 1_786_536_000 },
      { label: "weekly", used_percent: 34, window_seconds: 604_800, reset_at: 1_786_968_000 },
    ],
  });
});

test("a dormant five-hour window is kept with no scheduled reset", () => {
  const usage = parseClaudeUsage(
    {
      five_hour: { utilization: 0, resets_at: null },
      seven_day: { utilization: 28, resets_at: "2026-09-14T02:00:00.243080+00:00" },
    },
    "pro",
    "2026-09-11T13:41:39Z",
  );

  expect(usage?.windows).toEqual([
    { label: "5h", used_percent: 0, window_seconds: 18_000, reset_at: 0 },
    { label: "weekly", used_percent: 28, window_seconds: 604_800, reset_at: 1_789_351_200 },
  ]);
});

/**
 * The access token lasts 8h and nothing else on this machine renews it, so a
 * dashboard outlives it. Sending it anyway answers 401, and enough 401s earn a
 * 1h 429 that blanks the chip — which is exactly how "claude unavailable" got
 * on screen. The expired token must never leave this module.
 */
test("an expired access token is refreshed before the usage read, not after a 401", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-usage-"));
  writeFileSync(
    join(dir, ".credentials.json"),
    JSON.stringify({
      mcpOAuth: { untouched: true },
      claudeAiOauth: {
        accessToken: "expired",
        refreshToken: "refresh-token",
        expiresAt: Date.now() - 60_000,
        subscriptionType: "pro",
      },
    }),
  );

  const previousDir = process.env.CLAUDE_CONFIG_DIR;
  const realFetch = globalThis.fetch;
  process.env.CLAUDE_CONFIG_DIR = dir;
  const seen: string[] = [];
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const href = String(url);
    seen.push(href);
    if (href.includes("/v1/oauth/token")) {
      expect(JSON.parse(String(init?.body)).refresh_token).toBe("refresh-token");
      return new Response(
        JSON.stringify({ access_token: "fresh", refresh_token: "rotated", expires_in: 28_800 }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    // The whole point: the usage endpoint only ever sees the refreshed token.
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer fresh");
    return new Response(
      JSON.stringify({
        five_hour: { utilization: 42, resets_at: "2026-09-23T04:00:00Z" },
        seven_day: { utilization: 7, resets_at: "2026-09-29T04:00:00Z" },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    // Imported fresh so the module reads CLAUDE_CONFIG_DIR above and starts
    // with an empty memo; the module-level cache is per-process otherwise.
    const { readClaudeUsage } = await import(`./claude.ts?refresh-test=${Date.now()}`);
    const usage = await readClaudeUsage(true);

    expect(usage?.windows[0]?.used_percent).toBe(42);
    expect(seen[0]).toContain("/v1/oauth/token");

    // Written back, so the CLI and this dashboard keep sharing one credential —
    // including a rotated refresh token, and without disturbing mcpOAuth.
    const saved = JSON.parse(readFileSync(join(dir, ".credentials.json"), "utf8"));
    expect(saved.claudeAiOauth.accessToken).toBe("fresh");
    expect(saved.claudeAiOauth.refreshToken).toBe("rotated");
    expect(saved.mcpOAuth).toEqual({ untouched: true });
  } finally {
    globalThis.fetch = realFetch;
    if (previousDir === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = previousDir;
  }
});
