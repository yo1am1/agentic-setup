import { expect, test } from "bun:test";
import { parseAgyUsage } from "./agy.ts";

test("normalizes Antigravity (agy) 5h and weekly session usage by model groups", () => {
  const usage = parseAgyUsage(
    {
      groups: [
        {
          displayName: "Gemini Models",
          buckets: [
            {
              bucketId: "gemini-weekly",
              window: "weekly",
              resetTime: "2026-09-22T15:00:00Z",
              remainingFraction: 0.88,
            },
            {
              bucketId: "gemini-5h",
              window: "5h",
              resetTime: "2026-09-15T20:00:00Z",
              remainingFraction: 0.3,
            },
          ],
        },
        {
          displayName: "Claude and GPT models",
          buckets: [
            {
              bucketId: "3p-weekly",
              window: "weekly",
              resetTime: "2026-09-22T15:00:00Z",
              remainingFraction: 1.0,
            },
            {
              bucketId: "3p-5h",
              window: "5h",
              resetTime: "2026-09-15T20:00:00Z",
              remainingFraction: 0.95,
            },
          ],
        },
      ],
    },
    "Antigravity",
    "2026-09-15T17:00:00Z",
  );

  expect(usage).toEqual({
    plan: "Antigravity",
    source: "live",
    as_of: "2026-09-15T17:00:00Z",
    windows: [
      {
        label: "weekly",
        used_percent: 12,
        window_seconds: 604_800,
        reset_at: 1_790_089_200,
        group: "Gemini Models",
      },
      {
        label: "5h",
        used_percent: 70,
        window_seconds: 18_000,
        reset_at: 1_789_502_400,
        group: "Gemini Models",
      },
      {
        label: "weekly",
        used_percent: 0,
        window_seconds: 604_800,
        reset_at: 1_790_089_200,
        group: "Claude and GPT models",
      },
      {
        label: "5h",
        used_percent: 5,
        window_seconds: 18_000,
        reset_at: 1_789_502_400,
        group: "Claude and GPT models",
      },
    ],
  });
});

test("falls back to 5h window from models quotaInfo when passed fetchAvailableModels format", () => {
  const usage = parseAgyUsage(
    {
      models: {
        "gemini-3.6-flash-high": {
          quotaInfo: {
            remainingFraction: 0.75,
            resetTime: "2026-09-15T20:00:00Z",
          },
        },
      },
    },
    "Antigravity",
    "2026-09-15T17:00:00Z",
  );

  expect(usage).toEqual({
    plan: "Antigravity",
    source: "live",
    as_of: "2026-09-15T17:00:00Z",
    windows: [
      {
        label: "5h",
        used_percent: 25,
        window_seconds: 18_000,
        reset_at: 1_789_502_400,
      },
    ],
  });
});

test("returns null for empty quota or invalid payload", () => {
  expect(parseAgyUsage({}, "Antigravity")).toBeNull();
  expect(parseAgyUsage({ groups: [] }, "Antigravity")).toBeNull();
  expect(
    parseAgyUsage(
      {
        groups: [
          {
            buckets: [
              {
                window: "5h",
                remainingFraction: null,
              },
            ],
          },
        ],
      },
      "Antigravity",
    ),
  ).toBeNull();
});
