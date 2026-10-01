/**
 * SSSF visualizer server — JSON API over sssf.db, plus the built UI when
 * ./dist exists. Operator routes launch existing ADWs; workflow state still
 * comes exclusively from Python's tracer. Archive remains a review-only flag.
 *
 * There is no ingest endpoint and no websocket. The data path is
 * agents → sqlite → web ui, and the UI gets there by polling.
 *
 * TWO MODES, decided by whether a db was named explicitly:
 *
 *   single — one repo, the original behaviour. Routes are flat
 *            (/api/sessions/...) and there is no factories index.
 *              bun run server/index.ts --db /path/to/repo/adws/adw_data/sssf.db
 *              SSSF_DB=/path/to/sssf.db PORT=4600 bun run server/index.ts
 *
 *   multi  — every stamped repo under one or more roots, each addressed by
 *            name (/api/f/:factory/sessions/...) plus /api/factories. Roots
 *            are colon separated, like PATH.
 *              bun run server/index.ts
 *              SSSF_FACTORIES_ROOT=/home/user/VS:/home/user/work bun run server/index.ts
 *
 * Single mode is kept because a per-repo `just obs` is still the right tool
 * when you only care about the repo you are standing in.
 */
import { existsSync, realpathSync, statSync } from "node:fs";
import { basename, dirname, join, resolve, sep } from "node:path";
import { SssfDb, resolveDbPath } from "./db.ts";
import { FactoryRegistry, resolveFactoriesRoots } from "./factories.ts";
import { readCodexUsage } from "./codex.ts";
import { readClaudeUsage } from "./claude.ts";
import { readAgyUsage } from "./agy.ts";
import { guardOperator, launch, modelCatalog, operatorToken, OperatorError, projectOptions, stop, webRun } from './operator';
import { readInside } from './files.ts';
import { dshUrl } from './dsh.ts';
import type { FactoryEntry } from './factories';
import type {
  AgentPrompts,
  ApiError,
  FactorySummary,
  HealthResponse,
} from "../shared/types.ts";

const PORT = Number(process.env.PORT ?? 4600);
const DIST_DIR = resolve(import.meta.dir, "..", "dist");

/** An explicitly named db pins the server to one repo; otherwise it serves many. */
const SINGLE = Bun.argv.some((a) => a === "--db" || a.startsWith("--db=")) ||
  Boolean(process.env.SSSF_DB);

let singleDb: SssfDb | null = null;
let registry: FactoryRegistry | null = null;

if (SINGLE) {
  try {
    singleDb = new SssfDb(resolveDbPath());
  } catch (error) {
    console.error(`[sssf] ${(error as Error).message}`);
    process.exit(1);
  }
} else {
  registry = new FactoryRegistry(resolveFactoriesRoots());
  registry.watch();
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function notFound(message: string): Response {
  return json({ error: message } satisfies ApiError, 404);
}

/** Guard every handler so a malformed query can't take the server down mid-run. */
function safely(
  handler: (req: Request) => Response | Promise<Response>,
): (req: Request) => Promise<Response> {
  return async (req) => {
    try {
      guardOperator(req, PORT, !['GET', 'HEAD'].includes(req.method));
      return await handler(req);
    } catch (error) {
      console.error(`[sssf] ${req.method} ${new URL(req.url).pathname}:`, error);
      return json({ error: (error as Error).message } satisfies ApiError, error instanceof OperatorError ? error.status : 500);
    }
  };
}

/**
 * adw_ids and agent names are path segments on disk, so anything that isn't a
 * plain identifier is rejected outright rather than sanitized into something
 * that might still escape the sessions directory.
 */
const SAFE_SEGMENT = /^[A-Za-z0-9._-]+$/;

function isSafeSegment(value: string): boolean {
  return SAFE_SEGMENT.test(value) && value !== "." && value !== "..";
}

function param(req: Request, key: string): string {
  return decodeURIComponent(
    (req as Request & { params: Record<string, string> }).params[key] ?? "",
  );
}

/**
 * `?refresh=1` on health means the reader clicked the quota chip and wants the
 * figure as of now, not as of whenever the five minute memo was filled.
 * Refreshing is a metadata read upstream, so honouring it costs nothing.
 */
function refreshedProvider(req: Request): string | null {
  return new URL(req.url).searchParams.get("refresh");
}

async function subscriptionUsage(req: Request) {
  // `?refresh=codex`, `?refresh=claude`, or `?refresh=agy` — only the clicked chip's provider
  // skips its memo. Forcing all on every click sent multiple upstream requests per
  // click, and upstream endpoints answer bursts with 429 blocks.
  const fresh = refreshedProvider(req);
  const [codex, claude, agy] = await Promise.all([
    readCodexUsage(fresh === "codex"),
    readClaudeUsage(fresh === "claude"),
    readAgyUsage(fresh === "agy"),
  ]);
  return { codex, claude, agy };
}

function intQuery(req: Request, key: string, fallback: number): number {
  const raw = new URL(req.url).searchParams.get(key);
  if (raw === null || raw.trim() === "") return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Serve the built SPA if it has been built; otherwise point at the dev server. */
async function serveStatic(req: Request): Promise<Response> {
  const { pathname } = new URL(req.url);

  if (!existsSync(DIST_DIR)) {
    return new Response(
      `SSSF visualizer API is running on :${PORT}.\n\n` +
        `No ./dist build found. Run "bun run dev" for the Vite dev server ` +
        `(it proxies /api here), or "bun run build" to serve the UI from this process.\n`,
      { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  }

  // Reject traversal before touching the filesystem.
  const candidate = resolve(join(DIST_DIR, pathname));
  if (candidate === DIST_DIR || candidate.startsWith(DIST_DIR + "/")) {
    if (existsSync(candidate) && statSync(candidate).isFile()) {
      return new Response(Bun.file(candidate));
    }
  }

  // SPA fallback: breadcrumb routes are client-side.
  const indexHtml = join(DIST_DIR, "index.html");
  if (existsSync(indexHtml)) {
    return new Response(Bun.file(indexHtml), {
      headers: { "content-type": "text/html; charset=utf-8" },
    });
  }
  return notFound("not found");
}

/** Finds the db a request is about. The only thing that differs between modes. */
type DbResolver = (req: Request) => SssfDb | null;

/**
 * The session routes, generated once per mode.
 *
 * Both modes answer exactly the same questions about a session; they disagree
 * only on which db to ask. Generating them from one definition is what makes
 * "identical below the factory level" true in the server as well as the UI —
 * there is no second copy of these handlers to drift.
 */
function sessionRoutes(prefix: string, resolveDb: DbResolver) {
  const withDb =
    (handler: (req: Request, db: SssfDb) => Response | Promise<Response>) =>
    async (req: Request): Promise<Response> => {
      const factory = param(req, "factory");
      if (factory && !isSafeSegment(factory)) {
        return json({ error: "invalid factory" } satisfies ApiError, 400);
      }
      const database = resolveDb(req);
      // A freshly stamped project is launchable before its first trace exists.
      if (!database && new URL(req.url).pathname.endsWith('/sessions') && projectEntries().some(entry => entry.name === factory)) {
        return json([]);
      }
      if (!database) return notFound(`unknown factory ${factory}`);
      return handler(req, database);
    };

  return {
    [`${prefix}/sessions`]: safely(
      withDb((req, db) => json(db.sessions(intQuery(req, "limit", 200)))),
    ),

    [`${prefix}/sessions/:adw_id`]: safely(
      withDb((req, db) => {
        const detail = db.sessionDetail(param(req, "adw_id"));
        return detail ? json(detail) : notFound(`no session ${param(req, "adw_id")}`);
      }),
    ),

    // The one write. Archiving is review triage — it belongs to the reader, not
    // to the run — so it never touches anything a tracer wrote.
    [`${prefix}/sessions/:adw_id/archive`]: {
      POST: safely(
        withDb(async (req, db) => {
          const adwId = param(req, "adw_id");
          if (!isSafeSegment(adwId)) {
            return json({ error: "invalid adw_id" } satisfies ApiError, 400);
          }
          const body = (await req.json().catch(() => ({}))) as { archived?: unknown };
          const archived = body.archived === undefined ? true : Boolean(body.archived);
          return db.setArchived(adwId, archived)
            ? json({ adw_id: adwId, archived })
            : notFound(`no session ${adwId}`);
        }),
      ),
    },

    [`${prefix}/sessions/:adw_id/events`]: safely(
      withDb((req, db) =>
        json(
          db.events(
            param(req, "adw_id"),
            intQuery(req, "after", 0),
            intQuery(req, "limit", 500),
          ),
        ),
      ),
    ),

    [`${prefix}/sessions/:adw_id/envelopes`]: safely(
      withDb((req, db) => json(db.envelopes(param(req, "adw_id")))),
    ),

    [`${prefix}/sessions/:adw_id/gates`]: safely(
      withDb((req, db) => json(db.gates(param(req, "adw_id")))),
    ),

    // The exact prompts an agent was sent, read from the session dir. Files are
    // the raw record; the db has no copy of them.
    [`${prefix}/sessions/:adw_id/agents/:agent/prompts`]: safely(
      withDb(async (req, db) => {
        const adwId = param(req, "adw_id");
        const agent = param(req, "agent");
        if (!isSafeSegment(adwId) || !isSafeSegment(agent)) {
          return json({ error: "invalid adw_id or agent" } satisfies ApiError, 400);
        }
        if (!db.session(adwId)) return notFound(`no session ${adwId}`);

        const dir = resolve(db.sessionsDir, adwId, agent, "prompts");
        // Defense in depth: the segment check already forbids traversal.
        if (dir !== db.sessionsDir && !dir.startsWith(db.sessionsDir + sep)) {
          return json({ error: "invalid path" } satisfies ApiError, 400);
        }

        // A prompt file is absent whenever the agent never ran in this session —
        // a normal state, so it reads as null rather than an error.
        const read = async (name: string): Promise<string | null> => {
          const file = Bun.file(join(dir, `${name}.md`));
          return (await file.exists()) ? await file.text() : null;
        };
        return json({
          system: await read("system"),
          user: await read("user"),
        } satisfies AgentPrompts);
      }),
    ),
  };
}

/**
 * The factories index: one row per stamped repo.
 *
 * A factory whose db has gone unreadable is omitted and logged rather than
 * failing the request — an index of a dozen repos must not go dark because one
 * of them is mid-delete.
 */
function factoriesRoute(reg: FactoryRegistry) {
  return safely(() => {
    const summaries: FactorySummary[] = [];
    for (const entry of reg.list()) {
      const db = reg.getDb(entry.name);
      if (!db) {
        if (existsSync(entry.dbPath)) continue; // unreadable is not the same as never run
        summaries.push({ name: entry.name, path: entry.path, session_count: 0, running_count: 0,
          total_cost: 0, total_tokens: 0, last_started_at: null, recent_runs: [] });
        continue;
      }
      try {
        summaries.push({ name: entry.name, path: entry.path, ...db.factorySummary() });
      } catch (error) {
        console.error(`[sssf] factory ${entry.name}:`, error);
      }
    }
    return json(summaries);
  });
}

/**
 * Bun infers route keys as literals, which a mode-dependent object cannot
 * supply — the prefix is only known at runtime. Typing the table as a record
 * keeps the handlers checked while letting the key set vary.
 */
type RouteHandler =
  | ((req: Request) => Response | Promise<Response>)
  | { POST: (req: Request) => Response | Promise<Response> };

const routes: Record<string, RouteHandler> = SINGLE
  ? {
      "/api/health": safely(async (req) =>
        json({
          ok: true,
          mode: "single",
          db: singleDb!.path,
          journal_mode: singleDb!.journalMode,
          sessions: singleDb!.sessionCount(),
          ...(await subscriptionUsage(req)),
        } satisfies HealthResponse),
      ),
      ...sessionRoutes("/api", () => singleDb),
      '/api/factories': safely(() => json(projectEntries().map(entry => Object.assign({ name: entry.name, path: entry.path }, singleDb!.factorySummary())))),
      ...sessionRoutes('/api/f/:factory', req => param(req, 'factory') === projectEntries()[0]?.name ? singleDb : null),
    }
  : {
      "/api/health": safely(async (req) =>
        json({
          ok: true,
          mode: "multi",
          factories: registry!.list().length,
          roots: registry!.roots,
          ...(await subscriptionUsage(req)),
        } satisfies HealthResponse),
      ),
      "/api/factories": factoriesRoute(registry!),
      ...sessionRoutes("/api/f/:factory", (req) =>
        registry!.getDb(param(req, "factory")),
      ),
    };

function projectEntries(): FactoryEntry[] {
  if (registry) return registry.list();
  const path = resolve(dirname(singleDb!.path), '../..');
  return [{ name: basename(path), path, dbPath: singleDb!.path }];
}

function operatorProject(req: Request): FactoryEntry {
  const entry = projectEntries().find(project => project.name === param(req, 'factory'));
  if (!entry) throw new OperatorError('unknown project', 404);
  // Observation supports symlinked repos. Execution must remain under configured roots.
  if (registry && !registry.roots.some(root => existsSync(root) && realpathSync(entry.path).startsWith(realpathSync(root) + sep))) {
    throw new OperatorError('project resolves outside configured roots', 403);
  }
  return entry;
}

async function requestBody(req: Request): Promise<unknown> {
  if (req.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') {
    throw new OperatorError('send application/json', 415);
  }
  if (Number(req.headers.get('content-length')) > 65_536) throw new OperatorError('request too large', 413);
  const body = await req.text();
  if (body.length > 65_536) throw new OperatorError('request too large', 413);
  try { return JSON.parse(body); }
  catch { throw new OperatorError('invalid JSON'); }
}

Object.assign(routes, {
  // POST, not GET: this doesn't mutate anything, but it hands back a login
  // credential for a different service, and that deserves the same
  // x-sssf-token gate a write does — safely() derives the gate from the verb.
  '/api/reply-notifications': safely(async () => {
    const response = await fetch('http://127.0.0.1:3001/api/social/reply-notifications');
    return json(await response.json(), response.status);
  }),
  '/api/reply-notifications/:id/:action': { POST: safely(async req => {
    const response = await fetch(`http://127.0.0.1:3001/api/social/reply-notifications/${param(req, 'id')}/${param(req, 'action')}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(await requestBody(req)),
    });
    return json(await response.json(), response.status);
  }) },
  '/api/dsh-url': { POST: safely(async req => json({ url: await dshUrl(req.headers.get('host')) })) },
  '/api/operator': safely(async () => json({ token: operatorToken, enabled: process.platform === 'linux',
    projects: projectEntries().map(entry => {
      try { return projectOptions(entry); }
      catch (error) { return { name: entry.name, path: entry.path, configs: [], workflows: [], web_runs: [], error: (error as Error).message }; }
    }), ...(await modelCatalog()) })),
  '/api/f/:factory/launch': { POST: safely(async req => json(await launch(operatorProject(req), await requestBody(req)), 202)) },
  '/api/f/:factory/launches/:adw_id': safely(req => {
    const run = webRun(operatorProject(req), param(req, 'adw_id'));
    return run ? json(run) : notFound('no web launch record');
  }),
  '/api/f/:factory/launches/:adw_id/stop': { POST: safely(req => json(stop(operatorProject(req), param(req, 'adw_id')))) },
  // Read-only window into the repo a run worked in, so a path in the trace can
  // be opened where it is named instead of copied into an editor.
  '/api/f/:factory/files': safely(async req => {
    const entry = projectEntries().find(project => project.name === param(req, 'factory'));
    if (!entry) return notFound(`unknown factory ${param(req, 'factory')}`);
    return json(await readInside(entry.path, new URL(req.url).searchParams.get('path') ?? ''));
  }),
});

const server = Bun.serve({
  hostname: '127.0.0.1',
  port: PORT,
  maxRequestBodySize: 65_536,
  routes,

  fetch(req) {
    const { pathname } = new URL(req.url);
    if (pathname.startsWith("/api/")) return notFound(`no route ${pathname}`);
    return serveStatic(req);
  },
});

console.log(`[sssf] visualizer api  http://localhost:${server.port}`);
console.log(
  SINGLE
    ? `[sssf] db              ${singleDb!.path}  [journal_mode=${singleDb!.journalMode}]`
    : `[sssf] factories roots ${registry!.roots.join(", ")}  [${registry!.list().length} found]`,
);
console.log(
  existsSync(DIST_DIR)
    ? `[sssf] serving ui from  ${DIST_DIR}`
    : `[sssf] no ./dist — use "bun run dev" for the Vite dev server on :4601`,
);

process.on("SIGINT", () => {
  singleDb?.close();
  registry?.stop();
  process.exit(0);
});
