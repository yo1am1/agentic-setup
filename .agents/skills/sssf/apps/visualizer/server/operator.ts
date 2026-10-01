/** Local launch controls. Python ADWs still own all phases, gates and trace writes. */
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import {
  closeSync, existsSync, fstatSync, mkdirSync, openSync, readFileSync,
  readSync, readdirSync, readlinkSync, realpathSync, unlinkSync, writeFileSync,
} from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { Database } from 'bun:sqlite';
import type { FactoryEntry } from './factories';
import { FUSION_FLOWS, validFusionModels, validFusionSynthesizer } from '../shared/fusion';
import type { LaunchRequest, OperatorProject, RosterSummary, WebRun, WebRunDetail, WorkflowOption } from '../shared/types';

const execute = promisify(execFile);
const DATA = 'adws/adw_data';
const ID = /^web-[a-f0-9]{16}$/;
const ACTIVE = new Set(['starting', 'running', 'stopping']);
const observed = new Set<string>(); // this server still has the child's exit callback
export const operatorToken = crypto.randomUUID();
export const WORKFLOWS: WorkflowOption[] = [
  { id: 'fusion', label: 'Fusion plan (3–12 models; no build)', script: 'adw_fusion_plan.py', changes: false, commits: false },
  { id: 'fusion-sdlc', label: 'Fusion consensus plan, then verified SDLC', script: 'adw_fusion_sdlc.py', changes: true, commits: true },
  { id: 'sdlc', label: 'Base plan, build, checks, and tests', script: 'adw_plan_build_test.py', changes: true, commits: true },
  { id: 'plan', label: 'Plan only', script: 'adw_plan.py', changes: true, commits: false },
  { id: 'scout', label: 'Scout / research', script: 'adw_scout.py', changes: false, commits: false },
];

function engine(entry: FactoryEntry): string {
  return entry.enginePath ?? resolve(import.meta.dir, '../../../templates/adws');
}

export class OperatorError extends Error {
  constructor(message: string, readonly status = 400) { super(message); }
}

/**
 * Loopback on a port this server answers on, or an authority named in
 * `SSSF_TRUSTED_HOSTS` — a comma-separated list of `host` or `host:port`.
 *
 * Unset, that variable leaves the fence exactly loopback-only. A name belongs
 * in it only when something outside this process already authenticated the
 * peer (a Tailscale tailnet name reached over WireGuard, an authenticating
 * reverse proxy); a name a public DNS server can resolve does not qualify,
 * because that is the rebinding attack this fence exists to refuse. Listing
 * one widens *reachability* alone — every write still needs the operator
 * token. Loopback is answered before the variable is read, so the common
 * request never parses it.
 */
function trustedAuthority(value: URL, port: number): boolean {
  if (['localhost', '127.0.0.1', '[::1]'].includes(value.hostname)
    && [String(port), '4601'].includes(value.port)) return true;
  const allowed = new Set((process.env.SSSF_TRUSTED_HOSTS ?? '').split(',')
    .map(entry => entry.trim()).filter(Boolean));
  return allowed.has(value.host) || allowed.has(value.hostname);
}

/** Reject DNS rebinding and cross-site requests before exposing local controls. */
export function guardOperator(req: Request, port: number, write = false): void {
  const url = new URL(req.url);
  if (!trustedAuthority(url, port) || req.headers.get('sec-fetch-site') === 'cross-site') {
    throw new OperatorError('local requests only', 403);
  }
  const origin = req.headers.get('origin');
  if (origin) {
    let source: URL;
    try { source = new URL(origin); } catch { throw new OperatorError('untrusted origin', 403); }
    if (!trustedAuthority(source, port)) throw new OperatorError('untrusted origin', 403);
  }
  if (write && req.headers.get('x-sssf-token') !== operatorToken) {
    throw new OperatorError('refresh the page before using operator controls', 403);
  }
}

/**
 * Existing ancestors must resolve inside the project, including runtime dirs.
 *
 * `trusted` widens that to other roots the operator already serves factories
 * from: `just init` links a project's rosters at the factory owning the shared
 * engine, so refusing every symlink would refuse the supported layout. It is
 * passed only where a linked file is legitimate — never for session runtime,
 * which has no reason to leave the project it belongs to.
 */
function inside(root: string, relative: string, trusted: string[] = []): string {
  const target = resolve(root, relative);
  if (!target.startsWith(root + sep)) throw new OperatorError('path escapes project');
  let ancestor = target;
  while (!existsSync(ancestor)) ancestor = resolve(ancestor, '..');
  const actual = realpathSync(ancestor);
  const within = (base: string) => actual === base || actual.startsWith(base + sep);
  if (!within(root) && !trusted.some(within)) throw new OperatorError('symlink escapes project');
  return target;
}

/** Roots this factory may legitimately link into, resolved and existing. */
function trustedRoots(entry: FactoryEntry): string[] {
  const roots: string[] = [];
  for (const root of entry.trustedRoots ?? []) {
    try { roots.push(realpathSync(root)); } catch { /* a vanished root trusts nothing */ }
  }
  return roots;
}

export function projectOptions(entry: FactoryEntry): OperatorProject {
  const root = realpathSync(entry.path);
  const trusted = trustedRoots(entry);
  const configs = inside(root, 'adws/adw_sssf_config', trusted);
  const sessions = inside(root, `${DATA}/sessions`);
  const runs: WebRun[] = [];
  for (const id of existsSync(sessions) ? readdirSync(sessions).filter(name => ID.test(name)) : []) {
    const state = paths(root, id).state;
    if (existsSync(state)) {
      try { runs.push(JSON.parse(readFileSync(state, 'utf8')) as WebRun); }
      catch { /* A damaged launch record does not hide other projects. */ }
    }
  }
  return {
    name: entry.name, path: root,
    web_runs: runs.toSorted((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, 10),
    workflows: existsSync(configs) ? WORKFLOWS : [],
    configs: existsSync(configs) ? readdirSync(configs).filter(name => /^[\w.-]+\.ya?ml$/.test(name)
      && existsSync(inside(root, `adws/adw_sssf_config/${name}`, trusted)))
      .map(name => roster(join(configs, name), name)) : [],
  };
}

/**
 * Summarize a roster file for the launcher.
 *
 * Two rosters differ in the models each agent runs on and in what each agent
 * may write — never in their filenames. Reading them here is what lets the
 * picker show that difference instead of asking the engineer to remember it.
 */
/** A YAML list the engineer hand-edits may hold anything; keep only strings. */
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(item => typeof item === 'string') as string[] : [];
}

function roster(path: string, file: string): RosterSummary {
  try {
    const parsed = Bun.YAML.parse(readFileSync(path, 'utf8')) as {
      defaults?: { coding_agent?: string; model?: string; thinking?: string };
      fusion?: { use?: string; panel?: string[]; synthesizer?: string; openers?: string[];
        allow_single_family?: boolean;
        panels?: Record<string, { panel?: string[]; synthesizer?: string; openers?: string[];
          allow_single_family?: boolean }> };
      agents?: { name?: string; model?: string; thinking?: string; purpose?: string; writes?: string[] }[];
    };
    const defaults = parsed?.defaults ?? {};
    const fusion = parsed?.fusion ?? {};
    const model = String(defaults.model ?? 'unset');
    const thinking = String(defaults.thinking ?? 'unset');
    const panels = Object.fromEntries(Object.entries(fusion.panels ?? {}).map(([name, value]) =>
      [name, { panel: strings(value.panel),
        synthesizer: typeof value.synthesizer === 'string' ? value.synthesizer : '',
        openers: strings(value.openers), allowSingleFamily: value.allow_single_family === true }]));
    const selectedPanel = typeof fusion.use === 'string' ? fusion.use : 'default';
    const selected = selectedPanel === 'default' ? fusion : panels[selectedPanel];
    // Mirrors fusion.allow_single_family(): the default panel's flag is the
    // top-level one, a named panel's is its own. Reading only the named case
    // would refuse in the launcher a single-family panel the CLI accepts.
    const allowSingleFamily = selectedPanel === 'default'
      ? fusion.allow_single_family === true
      : panels[selectedPanel]?.allowSingleFamily === true;
    return {
      file,
      coding_agent: String(defaults.coding_agent ?? 'unset'),
      model,
      thinking,
      panel: strings(selected?.panel),
      synthesizer: typeof selected?.synthesizer === 'string' ? selected.synthesizer : '',
      openers: strings(selected?.openers),
      selectedPanel,
      allowSingleFamily,
      panels,
      agents: (parsed?.agents ?? []).filter(agent => agent?.name).map(agent => ({
        name: String(agent.name),
        model: String(agent.model ?? model),
        inherited: agent.model === undefined,
        thinking: String(agent.thinking ?? thinking),
        purpose: String(agent.purpose ?? ''),
        writes: agent.writes === undefined ? null : agent.writes ?? [],
      })),
    };
  } catch (error) {
    // An unreadable roster is not launchable at all, so the diversity floor
    // stays on: nothing here may opt out of it.
    return { file, coding_agent: 'unset', model: 'unset', thinking: 'unset', agents: [],
      panel: [], synthesizer: '', openers: [], selectedPanel: 'default',
      allowSingleFamily: false, panels: {}, error: (error as Error).message };
  }
}

export async function modelCatalog(): Promise<{ models: string[]; model_error: string | null }> {
  try {
    const { stdout } = await execute('pi', ['--list-models'], { timeout: 10_000, maxBuffer: 1_000_000 });
    const models = stdout.split('\n').map(line => line.trim().split(/\s+/))
      .filter(parts => parts.length >= 3 && parts[0] !== 'provider')
      .map(parts => `${parts[0]}/${parts[1]}`);
    return { models, model_error: null };
  } catch {
    return { models: [], model_error: 'Pi model catalog unavailable. Check Pi installation and login in your terminal.' };
  }
}

// ponytail: launching is Linux-only until an equally reliable process-identity
// check is implemented elsewhere. Observation continues to work on other OSes.
function processIdentity(pid: number): string | null {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, 'utf8');
    const fields = stat.slice(stat.lastIndexOf(')') + 2).split(' ');
    return fields[0] === 'Z' ? null : fields[19];
  } catch { return null; }
}

function ownsProcess(run: WebRun): boolean {
  return run.pid !== null && run.start_ticks !== null && processIdentity(run.pid) === run.start_ticks;
}

function paths(root: string, id: string) {
  if (!ID.test(id)) throw new OperatorError('invalid web run ID');
  const dir = inside(root, `${DATA}/sessions/${id}`);
  return { dir, state: inside(root, `${DATA}/sessions/${id}/web_launch.json`),
    log: inside(root, `${DATA}/sessions/${id}/web_output.log`), lock: inside(root, `${DATA}/sessions/.web-run.lock`) };
}

function release(root: string, id: string): void {
  const lock = paths(root, id).lock;
  if (existsSync(lock) && readFileSync(lock, 'utf8') === id) unlinkSync(lock);
}

function tail(path: string): string {
  if (!existsSync(path)) return '';
  const fd = openSync(path, 'r');
  try {
    const size = fstatSync(fd).size;
    const buffer = Buffer.alloc(Math.min(size, 16_384));
    readSync(fd, buffer, 0, buffer.length, Math.max(0, size - buffer.length));
    return buffer.toString('utf8');
  } finally { closeSync(fd); }
}

export function webRun(entry: FactoryEntry, id: string): WebRunDetail | null {
  const root = realpathSync(entry.path);
  const files = paths(root, id);
  if (!existsSync(files.state)) return null;
  const run = JSON.parse(readFileSync(files.state, 'utf8')) as WebRun;
  if (run.adw_id !== id) throw new OperatorError('invalid launch record', 409);
  if (ACTIVE.has(run.status) && !observed.has(files.state) && run.pid !== null && !ownsProcess(run)) {
    run.status = 'interrupted';
    run.ended_at = new Date().toISOString();
    run.error = 'Launcher process ended without a recorded exit status. Inspect the trace and output.';
    writeFileSync(files.state, JSON.stringify(run));
    release(root, id);
  }
  return { ...run, output: tail(files.log) };
}

/** Validate web input before acquiring a lock or creating a process. */
export function validateLaunch(entry: FactoryEntry, body: unknown): { root: string; input: LaunchRequest; flow: WorkflowOption } {
  const input = body as LaunchRequest;
  const options = projectOptions(entry);
  const flow = options.workflows.find(value => value.id === input?.workflow);
  if (!input || input.runtime !== 'pi' || !flow || !options.configs.some(item => item.file === input.config && !item.error)) {
    throw new OperatorError('choose an available Pi workflow and roster');
  }
  if (typeof input.prompt !== 'string' || !input.prompt.trim() || input.prompt.length > 32_000) {
    throw new OperatorError('request must contain 1–32000 characters');
  }
  if (flow.changes && input.allow_changes !== true) throw new OperatorError('confirm repository changes before launching');
  if (FUSION_FLOWS.has(flow.id)) {
    // No panel named: the simplified launcher's normal case. Fall back to the
    // target roster's own `fusion:` panel — pre-flight-checked here so a bad
    // roster fails at launch, not three phases into a run — and never sent as
    // an explicit --models argv; the ADW process resolves it from the same
    // config file, so there is exactly one place this logic lives.
    if (input.models === undefined) {
      const target = options.configs.find(item => item.file === input.config);
      const chosen = input.panel ? target?.panels[input.panel] : target;
      if (!target || target.error || !chosen || chosen.panel.length < 3 || chosen.panel.length > 12
          || new Set(chosen.panel).size !== chosen.panel.length
          || (!chosen.allowSingleFamily && !validFusionModels(chosen.panel))) {
        throw new OperatorError(
          `${input.config} has no usable Fusion panel — choose a configured panel or use --models`);
      }
    } else if (!Array.isArray(input.models)
        || input.models.some(model => typeof model !== 'string' || !/^[\w.-]+\/[^\s]+$/.test(model))
        || !validFusionModels(input.models)) {
      throw new OperatorError('Fusion requires 3–12 distinct models from at least two families; Claude must use OpenRouter or OmniRoute');
    }
    if (input.synthesizer !== undefined
        && (typeof input.synthesizer !== 'string'
            || (input.models !== undefined && !validFusionSynthesizer(input.synthesizer, input.models)))) {
      throw new OperatorError('The synthesizer must be one of the discussion models');
    }
  }
  const root = options.path;
  const config = Bun.YAML.parse(readFileSync(
    inside(root, `adws/adw_sssf_config/${input.config}`, trustedRoots(entry)), 'utf8')) as {
    defaults?: { data_dir?: string }; observability?: { db?: string };
  } | null;
  if ((config?.defaults?.data_dir ?? DATA) !== DATA || (config?.observability?.db ?? `${DATA}/sssf.db`) !== `${DATA}/sssf.db`) {
    throw new OperatorError('Web launches currently require the standard adws/adw_data trace location');
  }
  return { root, input, flow };
}

/** One web launch per project. CLI runs are checked but should not race web launches. */
export async function launch(entry: FactoryEntry, body: unknown): Promise<WebRun> {
  if (process.platform !== 'linux') throw new OperatorError('Web launching currently requires Linux', 409);
  const { root, input, flow } = validateLaunch(entry, body);
  const git = await execute('git', ['rev-parse', '--show-toplevel'], { cwd: root, timeout: 5000 });
  if (realpathSync(git.stdout.trim()) !== root) throw new OperatorError('project must be a Git repository root');
  if (flow.commits) {
    const dirty = await execute('git', ['status', '--porcelain'], { cwd: root, timeout: 5000 });
    if (dirty.stdout.trim()) throw new OperatorError('Commit or stash existing changes first; this workflow commits the working tree', 409);
    try { await execute('git', ['check-ignore', '--quiet', `${DATA}/sessions/web-runtime-check`], { cwd: root, timeout: 5000 }); }
    catch { throw new OperatorError('Ignore adws/adw_data/sessions/ before launching a committing workflow', 409); }
  }
  if (existsSync(entry.dbPath)) {
    const db = new Database(entry.dbPath, { readonly: true });
    try {
      const rows = db.query<{ pid: number }, []>("SELECT pid FROM processes WHERE kind='adw' AND ended_at IS NULL").all();
      const running = rows.some(row => {
        if (!processIdentity(row.pid)) return false;
        try { return realpathSync(readlinkSync(`/proc/${row.pid}/cwd`)) === root; }
        catch { return true; } // cannot disprove ownership safely
      });
      if (running) throw new OperatorError('A recorded workflow is still running in this project', 409);
    } finally { db.close(); }
  }
  const id = `web-${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`;
  const files = paths(root, id);
  mkdirSync(inside(root, `${DATA}/sessions`), { recursive: true });
  if (existsSync(files.lock)) {
    const previous = readFileSync(files.lock, 'utf8');
    webRun(entry, previous); // recover a dead launch after a server restart
  }
  try { writeFileSync(files.lock, id, { flag: 'wx' }); }
  catch { throw new OperatorError('This project already has a web launch. Open its run or resolve its stale launch lock.', 409); }
  const run: WebRun = { adw_id: id, workflow: flow.id, status: 'starting', pid: null, start_ticks: null,
    started_at: new Date().toISOString(), ended_at: null, exit_code: null, error: null };
  try {
    mkdirSync(files.dir, { recursive: true });
    writeFileSync(files.state, JSON.stringify(run));
    const request = inside(root, `${DATA}/sessions/${id}/web_request.md`);
    writeFileSync(request, input.prompt);
    const args = ['run', resolve(engine(entry), flow.script), request, '--config', `adws/adw_sssf_config/${input.config}`, '--adw-id', id];
    if (FUSION_FLOWS.has(flow.id)) {
      // A named panel is an explicit override; omitted, the ADW process reads
      // the roster's own fusion: block itself — the single place that default
      // is ever resolved, so the web and CLI paths can never quietly disagree.
      if (input.models !== undefined) args.push('--models', ...input.models);
      if (input.panel) args.push('--panel', input.panel);
      if (input.synthesizer) args.push('--synthesizer-model', input.synthesizer);
    }
    const output = openSync(files.log, 'a');
    let child;
    try { child = spawn('uv', args, { cwd: root, detached: true, stdio: ['ignore', output, output] }); }
    finally { closeSync(output); }
    run.pid = child.pid ?? null;
    run.start_ticks = run.pid === null ? null : processIdentity(run.pid);
    run.status = 'running';
    writeFileSync(files.state, JSON.stringify(run));
    observed.add(files.state);
    const finish = (code: number | null, error: string | null) => {
      observed.delete(files.state);
      try {
        const current = paths(root, id);
        const stopping = existsSync(current.state) && JSON.parse(readFileSync(current.state, 'utf8')).status === 'stopping';
        run.status = stopping ? 'cancelled' : code === 0 ? 'success' : 'fail';
        run.exit_code = code;
        run.error = error;
        run.ended_at = new Date().toISOString();
        writeFileSync(current.state, JSON.stringify(run));
        release(root, id);
      } catch (failure) { console.error(`[sssf] could not finalize ${id}:`, failure); }
    };
    child.once('error', error => finish(null, error.message));
    child.once('exit', (code, signal) => finish(code, signal ? `Terminated by ${signal}` : null));
    return run;
  } catch (error) {
    release(root, id);
    throw error;
  }
}

export function stop(entry: FactoryEntry, id: string): WebRunDetail {
  const run = webRun(entry, id);
  if (!run) throw new OperatorError('web launch not found', 404);
  if (!ACTIVE.has(run.status)) return run;
  if (!ownsProcess(run)) throw new OperatorError('Cannot safely identify this launcher process', 409);
  run.status = 'stopping';
  const { output: _output, ...state } = run;
  writeFileSync(paths(realpathSync(entry.path), id).state, JSON.stringify(state));
  // Each launcher owns a fresh process group. Never signal a recycled PID.
  process.kill(-run.pid!, 'SIGTERM');
  return run;
}
