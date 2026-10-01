/**
 * A read-only window onto SSSF's own documentation, for the SSSF preset only.
 *
 * That preset otherwise has exactly one tool (`sssf`) and no filesystem: "the
 * factory does the work" (see agent.cordis.yml). But not having a filesystem
 * left the operator unable to consult the documentation this project actually
 * ships — CLAUDE.md, the cookbooks, the references, the same `.agents/skills/
 * sssf/SKILL.md` that pi and dsh's own bash-tool sessions already read. A
 * general `dsh-tool-fs` mount would fix that, but it registers `write`/`edit`
 * unconditionally (no read-only config exists) — the exact capability this
 * preset was built to deny.
 *
 * So: one narrow tool, read-only by construction (no write, no edit, no glob
 * outside the allowlist below), scoped to documentation and nothing else in
 * the repo. Same realpath boundary check as the web visualizer's own repo
 * browser (`apps/visualizer/server/files.ts`) — a symlink pointing outside
 * the allowed root is refused, not followed.
 *
 * Imports nothing but node: builtins — same reason as tool-sssf.js: a preset
 * directory sits outside the harness install and cannot resolve its packages.
 */
import { readFileSync, readdirSync, realpathSync, statSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

export const name = 'tool-sssf-docs';
export const inject = ['tools'];

/**
 * Every doc root the tool may read, relative to the linked factory's root.
 * A single file is read whole; a directory is listed and every `.md` inside
 * it (one level, no recursion) is readable. Nothing outside this list is
 * reachable, however the path is written or symlinked.
 */
const ROOTS = [
  { path: 'CLAUDE.md', kind: 'file', about: "this factory's own architecture doc" },
  { path: '.claude/skills/sssf/SKILL.md', kind: 'file', about: 'the Claude Code skill: startup steps and where to read next' },
  { path: '.agents/skills/sssf/SKILL.md', kind: 'file', about: 'exact CLI commands for every workflow, and the safety rules around them (written for a shell-having agent — read it for the rules and shapes, not to run its examples yourself)' },
  { path: '.claude/skills/sssf/cookbooks', kind: 'dir', about: 'how-to guides: installing, running an ADW, writing prompts, editing config' },
  { path: '.claude/skills/sssf/references', kind: 'dir', about: 'schema and mechanism reference: config fields, the envelope/handoff contract, observability' },
];

/** First `# Heading` or `description:` frontmatter line, for a one-line catalog entry. */
function summarize(text) {
  const heading = /^#\s+(.+)$/m.exec(text);
  if (heading) return heading[1].trim();
  const description = /^description:\s*"?([^"\n]+)"?/m.exec(text);
  return description ? description[1].trim() : '';
}

/** Resolve `relative` under `root`, refusing anything a realpath check finds outside it. */
function resolveInside(root, relative) {
  const target = resolve(root, relative);
  const realRoot = realpathSync(root);
  let realTarget;
  try {
    realTarget = realpathSync(target);
  } catch {
    return { error: `no such path: ${relative}` };
  }
  if (realTarget !== realRoot && !realTarget.startsWith(realRoot + sep)) {
    return { error: `${relative} resolves outside the factory` };
  }
  return { path: realTarget };
}

/** The one allowlisted root (file or directory) `relative` falls under, if any. */
function findRoot(relative) {
  const normalized = relative.replace(/^[/\\]+/, '');
  return ROOTS.find((entry) =>
    entry.kind === 'file' ? entry.path === normalized : normalized.startsWith(`${entry.path}/`) || normalized === entry.path);
}

export function apply(ctx) {
  ctx.tools.register({
    name: 'sssf_docs',
    description:
      'Read SSSF\'s own documentation — never code, never anything outside the list below. '
      + '`list` (with no path) enumerates every readable document; `read` returns one, by the exact '
      + 'path `list` gave you. Load one of these before answering an architecture question, before '
      + 'picking a workflow you are unsure about, or whenever the `sssf` tool\'s own guidance is not '
      + 'enough — this is how you check rather than guess.\n\n'
      + 'What is readable: '
      + ROOTS.map((r) => `\`${r.path}\` (${r.about})`).join('; ') + '.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['action', 'project'],
      properties: {
        action: { type: 'string', enum: ['list', 'read'], description: 'list every document, or read one.' },
        project: { type: 'string', description: 'Absolute path to the linked factory repository — the same path you pass to the `sssf` tool.' },
        path: { type: 'string', description: 'Required for `read`: the exact path a `list` result gave you.' },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['ok', 'detail'],
        properties: { ok: { type: 'boolean' }, detail: { type: 'string' } },
      },
      render: (_args, value) => [{ type: 'text', text: value.detail }],
    },

    async execute(args) {
      const fail = (detail) => ({ ok: false, detail });
      if (typeof args.project !== 'string' || !args.project.startsWith('/')) {
        return fail('needs an absolute project path — the same one you pass to the sssf tool.');
      }
      let root;
      try {
        root = realpathSync(args.project);
      } catch {
        return fail(`no such directory: ${args.project}`);
      }

      if (args.action === 'list') {
        const rows = [];
        for (const entry of ROOTS) {
          const resolved = resolveInside(root, entry.path);
          if (resolved.error) continue; // this factory may not carry every root
          if (entry.kind === 'file') {
            let text = '';
            try { text = readFileSync(resolved.path, 'utf8'); } catch { /* listed as present, unreadable stays out */ }
            rows.push(`${entry.path} — ${summarize(text) || entry.about}`);
            continue;
          }
          let names;
          try { names = readdirSync(resolved.path); } catch { continue; }
          for (const name of names.sort()) {
            if (!name.endsWith('.md')) continue;
            const filePath = join(entry.path, name);
            let text = '';
            try { text = readFileSync(join(resolved.path, name), 'utf8'); } catch { /* skip unreadable */ }
            rows.push(`${filePath} — ${summarize(text) || entry.about}`);
          }
        }
        return { ok: true, detail: rows.length ? rows.join('\n') : 'No SSSF documentation found in this factory.' };
      }

      if (args.action === 'read') {
        if (typeof args.path !== 'string' || args.path.trim() === '') return fail('read needs a path from a prior list call.');
        const owner = findRoot(args.path);
        if (owner === undefined) return fail(`${args.path} is not one of the readable documents — call list first.`);
        const resolved = resolveInside(root, args.path);
        if (resolved.error) return fail(resolved.error);
        if (statSync(resolved.path).isDirectory()) return fail(`${args.path} is a directory — read one of its files instead.`);
        let text;
        try {
          text = readFileSync(resolved.path, 'utf8');
        } catch (error) {
          return fail(`could not read ${args.path}: ${error.message}`);
        }
        return { ok: true, detail: text };
      }

      return fail(`Unknown action: ${args.action}`);
    },
  });
}
