/**
 * The single tool the SSSF mode exposes.
 *
 * Every workflow is a detached Docker container running an existing ADW. This
 * file owns no workflow logic: it validates arguments and drives `docker`.
 * `docker/sssf.sh` inside the image maps a workflow name onto its ADW script,
 * and the Python ADWs own phases, gates, and commits exactly as they do from
 * the CLI or the web launcher.
 *
 * It imports nothing but node: builtins on purpose — a preset directory sits
 * outside the harness install, so it cannot resolve the harness's own packages.
 */
import { execFile } from 'node:child_process';
import { mkdirSync, writeFileSync, realpathSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export const name = 'tool-sssf';
export const inject = ['tools'];

const IMAGE = 'sssf-runner';

/** What the model may start, and what each one is allowed to do to the repo. */
export const WORKFLOWS = {
  'scout': { writes: false, commits: false, about: 'read-only research; reports where things live' },
  'plan': { writes: false, commits: false, about: 'one agent turns the request into an implementable plan' },
  'fusion-plan': { writes: false, commits: false, about: 'a panel of models debates to a consensus plan; never builds' },
  'sdlc': { writes: true, commits: true, about: 'plan, independent tests, build, checks, mutation-backed review, docs' },
  'fusion-sdlc': { writes: true, commits: true, about: 'consensus plan, then the full verified SDLC' },
};

/** Run a command to completion. Never through a shell. */
function run(file, args) {
  return new Promise((resolve) => {
    execFile(file, args, { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }, (error, stdout, stderr) => {
      resolve({ stdout: stdout ?? '', stderr: stderr ?? '', failed: error != null });
    });
  });
}

async function git(project, args) {
  const result = await run('git', ['-C', project, ...args]);
  return result.failed ? undefined : result.stdout.trim();
}

/**
 * Everything that must hold before a workflow may start.
 *
 * The same bar the web launcher applies, for the same reason: a committing
 * workflow that starts on a dirty tree sweeps unrelated work into an agent's
 * commit, and one that starts outside a linked factory fails three phases in
 * instead of here.
 * @returns the reason to refuse, or undefined when the run may proceed.
 */
export async function preflight(project, flow, allowChanges) {
  if (!existsSync(join(project, 'adws/adw_modules'))) {
    return `${project} is not a linked SSSF factory (no adws/adw_modules). Run \`just init\` there first.`;
  }
  const top = await git(project, ['rev-parse', '--show-toplevel']);
  if (top === undefined || realpathSync(top) !== realpathSync(project)) {
    return `${project} must be the root of a Git repository.`;
  }
  if (!flow.writes) return undefined;
  if (allowChanges !== true) {
    return `${flow.id} changes the repository and commits. Re-call with allow_changes: true once the user has asked for that.`;
  }
  if (flow.commits && (await git(project, ['status', '--porcelain'])) !== '') {
    return 'Commit or stash the working tree first; this workflow commits what it finds.';
  }
  return undefined;
}

/** One string names both the container and the ADW session. */
function newRunId() {
  return `dsh-${Date.now().toString(16)}${Math.random().toString(16).slice(2, 8)}`;
}

const DESCRIPTION =
  'Run and observe Super Simple Software Factory workflows: deterministic Python orchestration driving bounded coding agents, executed in a Docker container against a repository `just init` has linked to the factory engine.\n\n'
  + 'Workflows: '
  + Object.entries(WORKFLOWS).map(([id, f]) => `\`${id}\` — ${f.about}`).join('; ')
  + '.\n\n'
  + 'Actions: `start` launches a workflow and returns a run_id immediately; `status` reports whether it is still working and how it ended; `logs` returns output from an offset so repeated polls return only what is new; `stop` ends a run; `list` shows runs this harness started.\n\n'
  + 'A run keeps working after `start` returns — poll `status` and read `logs` rather than waiting inside one call. '
  + '`sdlc` and `fusion-sdlc` write to the repository and commit, so they need allow_changes: true and a clean working tree; `scout`, `plan`, and `fusion-plan` never write and are always safe to run to inform an answer.';

export function apply(ctx) {
  ctx.tools.register({
    name: 'sssf',
    description: DESCRIPTION,
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['action'],
      properties: {
        action: { type: 'string', enum: ['start', 'status', 'logs', 'stop', 'list'], description: 'What to do.' },
        workflow: { type: 'string', enum: Object.keys(WORKFLOWS), description: 'Which workflow to start. Required for `start`.' },
        prompt: { type: 'string', description: 'The request the factory works from. Required for `start`. Every agent in the chain reads it, so write it deliberately: the same intent in sharper words, real paths, and a stated "done means".' },
        project: { type: 'string', description: 'Absolute path to the linked factory repository. Required for `start`.' },
        config: { type: 'string', description: 'Roster filename under adws/adw_sssf_config/. Defaults to sssf.config.yaml.' },
        allow_changes: { type: 'boolean', description: 'Required for `sdlc` and `fusion-sdlc`: confirms the user asked for this repository to be changed and committed.' },
        run_id: { type: 'string', description: 'The run to act on. Required for `status`, `logs`, and `stop`.' },
        offset: { type: 'number', description: 'For `logs`: skip this many leading characters. Pass back the offset the previous call returned.' },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['ok', 'detail'],
        properties: {
          ok: { type: 'boolean' },
          detail: { type: 'string' },
          run_id: { type: 'string' },
          status: { type: 'string' },
          exit_code: { type: 'number' },
          offset: { type: 'number' },
        },
      },
      render: (_args, value) => [{ type: 'text', text: value.detail }],
    },

    async execute(args) {
      const fail = (detail) => ({ ok: false, detail });

      if (args.action === 'list') {
        const result = await run('docker', ['ps', '-a', '--filter', 'name=dsh-', '--format', '{{.Names}}\t{{.Status}}']);
        const rows = result.stdout.trim();
        return { ok: true, detail: rows === '' ? 'No SSSF runs started from this harness.' : rows };
      }

      if (args.action === 'start') {
        if (args.workflow === undefined) return fail('start needs a workflow.');
        if (typeof args.prompt !== 'string' || args.prompt.trim() === '') return fail('start needs a prompt.');
        if (args.prompt.length > 32000) return fail('That prompt is too long (32000 characters maximum).');
        if (typeof args.project !== 'string' || !args.project.startsWith('/')) return fail('start needs an absolute project path.');
        if (!existsSync(args.project)) return fail(`No such directory: ${args.project}`);

        const flow = { id: args.workflow, ...WORKFLOWS[args.workflow] };
        const project = realpathSync(args.project);
        const refusal = await preflight(project, flow, args.allow_changes);
        if (refusal !== undefined) return fail(refusal);

        // The prompt reaches the ADW as a file, so nothing in it is ever read
        // as an argument or a shell word. It is staged inside the run's own
        // session directory — already bind-mounted, already gitignored — so the
        // container needs no second mount and the request stays beside the
        // trace it produced.
        const id = newRunId();
        const sessionDir = join(project, 'adws/adw_data/sessions', id);
        mkdirSync(sessionDir, { recursive: true });
        writeFileSync(join(sessionDir, 'request.md'), args.prompt);
        const started = await run('docker', [
          'run', '--detach', '--name', id,
          '--network', 'host',                                   // the ADWs call the local OmniRoute gateway
          '--user', `${process.getuid()}:${process.getgid()}`,   // commits land as the host user, not root
          '--volume', `${project}:/workspace`,
          // Pi writes its own lock and trust files, so its config cannot be
          // mounted read-only.
          '--volume', `${join(homedir(), '.pi')}:/home/node/.pi`,
          '--env', 'HOME=/home/node',
          IMAGE,
          flow.id, `adws/adw_data/sessions/${id}/request.md`,
          `adws/adw_sssf_config/${args.config ?? 'sssf.config.yaml'}`, id,
        ]);
        if (started.failed) {
          const missing = /Unable to find image|No such image/.test(started.stderr);
          return fail(`Could not start the run: ${started.stderr.trim()}`
            + (missing ? `\n\nBuild the image once: docker build -f Dockerfile.sssf -t ${IMAGE} ${project}` : ''));
        }
        return {
          ok: true,
          run_id: id,
          detail: `Started ${flow.id} as ${id}. It keeps working after this call — poll action: "status", and read output with action: "logs".`,
        };
      }

      if (typeof args.run_id !== 'string' || args.run_id === '') return fail(`${args.action} needs a run_id.`);

      if (args.action === 'status') {
        const state = await run('docker', ['inspect', '-f', '{{.State.Status}} {{.State.ExitCode}}', args.run_id]);
        if (state.failed) return fail(`No run named ${args.run_id}.`);
        const [status, code] = state.stdout.trim().split(' ');
        const exit = Number(code);
        return {
          ok: true,
          status,
          ...(status === 'running' ? {} : { exit_code: exit }),
          detail: status === 'running'
            ? `${args.run_id} is still working.`
            : `${args.run_id} ${exit === 0 ? 'finished successfully' : `failed with exit code ${exit}`}. Read its output with action: "logs".`,
        };
      }

      if (args.action === 'logs') {
        const result = await run('docker', ['logs', args.run_id]);
        const all = result.stdout + result.stderr;
        if (result.failed && all.trim() === '') return fail(`No run named ${args.run_id}.`);
        const offset = Number.isFinite(args.offset) && args.offset > 0 ? args.offset : 0;
        const slice = all.slice(offset);
        return { ok: true, offset: all.length, detail: slice === '' ? '(no new output)' : slice };
      }

      if (args.action === 'stop') {
        const result = await run('docker', ['stop', args.run_id]);
        return result.failed
          ? fail(`Could not stop ${args.run_id}: ${result.stderr.trim()}`)
          : { ok: true, detail: `Stopped ${args.run_id}.` };
      }

      return fail(`Unknown action: ${args.action}`);
    },
  });
}
