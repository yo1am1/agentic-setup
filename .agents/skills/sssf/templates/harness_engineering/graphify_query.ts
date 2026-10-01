/**
 * graphify_query — one semantic code-graph lookup in place of a grep chain.
 *
 * Read-only by construction: it runs `graphify query` against the repo's
 * prebuilt index at graphify-out/graph.json and returns the answer. It never
 * builds or updates the index — extraction costs LLM tokens, which a read-only
 * planning seat must not spend. No index (or no CLI) → a one-line fallback
 * notice, and the agent uses grep/find instead.
 *
 * Usage: pi -e extensions/graphify_query.ts, then the agent has a
 * `graphify_query` tool (must also be named in its --tools allowlist).
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
const { spawn } = require("child_process") as any;
import * as fs from "fs";
import * as path from "path";

const GRAPH = path.join("graphify-out", "graph.json");
const TIMEOUT_MS = 90_000;
const MAX_OUTPUT = 8000;

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "graphify_query",
    description:
      "Semantic search over this repository's graphify knowledge graph (graphify-out/graph.json). " +
      "One call answers 'where does X live', 'what calls Y', 'how do A and B relate' — the questions " +
      "that otherwise take a whole grep→read→grep chain. Use it BEFORE grep for architecture and " +
      "relationship questions; still use read/grep/find to pin the exact path:line evidence your " +
      "proposal cites. When it reports there is no index, the repo has no knowledge graph — use " +
      "grep/find and do not call this tool again in this session.",
    parameters: Type.Object({
      question: Type.String({ description: "Natural-language question about the codebase" }),
      budget: Type.Optional(Type.Number({ description: "Answer size cap in tokens (default 1200)" })),
    }),
    execute: async (_callId, args, signal) => {
      if (!fs.existsSync(path.join(process.cwd(), GRAPH))) {
        return { content: [{ type: "text", text:
          `No graphify index at ${GRAPH} — this repo has not been indexed. ` +
          "Answer with read/grep/find instead, and do not retry graphify_query in this session." }] };
      }
      const budget = Math.max(200, Math.min(Math.trunc(args.budget ?? 1200), 4000));
      return await new Promise((resolve) => {
        const proc = spawn("graphify", ["query", args.question, "--budget", String(budget)],
          { stdio: ["ignore", "pipe", "pipe"] });
        let out = "";
        let err = "";
        const timer = setTimeout(() => proc.kill("SIGTERM"), TIMEOUT_MS);
        if (signal) signal.addEventListener("abort", () => proc.kill("SIGTERM"), { once: true });
        proc.stdout.setEncoding("utf8").on("data", (chunk: string) => { out += chunk; });
        proc.stderr.setEncoding("utf8").on("data", (chunk: string) => { err += chunk; });
        proc.on("close", (code: number | null) => {
          clearTimeout(timer);
          const text = (code === 0 ? out.trim() : "") ||
            `graphify query failed (${code === null ? "timeout" : `exit ${code}`}): ` +
            `${err.trim() || out.trim() || "no output"}. Use read/grep/find instead.`;
          resolve({ content: [{ type: "text", text: text.slice(0, MAX_OUTPUT) }] });
        });
        proc.on("error", (error: Error) => {
          clearTimeout(timer);
          resolve({ content: [{ type: "text", text:
            `graphify CLI unavailable (${error.message}). Use read/grep/find instead, ` +
            "and do not retry graphify_query in this session." }] });
        });
      });
    },
  });
}
