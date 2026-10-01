import { afterEach, expect, test } from 'bun:test';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { FactoryRegistry } from './factories';
import { guardOperator, launch, operatorToken, projectOptions, stop, validateLaunch, webRun } from './operator';
import type { LaunchRequest } from '../shared/types';

const temporary: string[] = [];
afterEach(() => { for (const path of temporary.splice(0)) rmSync(path, { recursive: true, force: true }); });

function project(script = "print('web workflow finished', flush=True)\n") {
  const base = mkdtempSync(join(tmpdir(), 'sssf-operator-test-'));
  temporary.push(base);
  const root = join(base, 'product');
  mkdirSync(join(root, 'adws/adw_sssf_config'), { recursive: true });
  writeFileSync(join(root, '.gitignore'), 'adws/adw_data/sessions/\n');
  writeFileSync(join(root, 'adws/adw_scout.py'), '# /// script\n# dependencies = []\n# ///\n' + script);
  writeFileSync(join(root, 'adws/adw_plan.py'), '# fake planning workflow\n');
  writeFileSync(join(root, 'adws/adw_plan_build_test.py'), '# fake committing workflow, must never run in this test\n');
  writeFileSync(join(root, 'adws/adw_fusion_plan.py'), '# fake planning workflow\n');
  writeFileSync(join(root, 'adws/adw_sssf_config/sssf.config.yaml'), 'defaults:\n  data_dir: adws/adw_data\n');
  execFileSync('git', ['init', '-q'], { cwd: root });
  return { base, name: 'product', path: root, dbPath: join(root, 'adws/adw_data/sssf.db'),
    enginePath: join(root, 'adws') };
}

const input: LaunchRequest = { runtime: 'pi', workflow: 'scout', config: 'sssf.config.yaml',
  prompt: 'check this product', models: [], allow_changes: false };

async function finished(entry: ReturnType<typeof project>, id: string) {
  for (let i = 0; i < 200; i++) {
    const state = webRun(entry, id)!;
    if (!['starting', 'running', 'stopping'].includes(state.status)) return state;
    // Polling depends on the previous status; these waits cannot run in parallel.
    // oxlint-disable-next-line no-await-in-loop
    await Bun.sleep(25);
  }
  throw new Error('web launch did not finish');
}

test('stamped project is discoverable before its first trace DB', () => {
  const entry = project();
  const registry = new FactoryRegistry([entry.base]);
  expect(registry.list().map(value => value.name)).toEqual(['product']);
  expect(registry.getDb('product')).toBeNull();
  expect(registry.list()).toHaveLength(1);
  expect(projectOptions(entry).workflows.map(value => value.id)).toContain('scout');
  registry.stop();
});

test('a roster is summarized by what differs: model per agent, and access', () => {
  const entry = project();
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/frontier.yaml'),
    'defaults:\n  coding_agent: pi\n  model: anthropic/claude-opus-5\n  thinking: high\n' +
    'agents:\n' +
    '  - name: builder\n    purpose: build it\n' +
    '  - name: reviewer\n    model: google/gemini-3.8-flash\n    writes: []\n' +
    '  - name: documenter\n    writes:\n      - docs/\n');
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/broken.yaml'), 'defaults: [oops\n');

  const rosters = projectOptions(entry).configs;
  const frontier = rosters.find(item => item.file === 'frontier.yaml')!;
  expect(frontier).toMatchObject({ coding_agent: 'pi', model: 'anthropic/claude-opus-5', thinking: 'high' });
  // An agent with no model of its own runs the default, and says so.
  expect(frontier.agents[0]).toMatchObject({ name: 'builder', model: 'anthropic/claude-opus-5', inherited: true, writes: null });
  expect(frontier.agents[1]).toMatchObject({ name: 'reviewer', model: 'google/gemini-3.8-flash', inherited: false, writes: [] });
  expect(frontier.agents[2].writes).toEqual(['docs/']);

  // An unreadable roster is still listed — and refused at launch, not silently.
  expect(rosters.find(item => item.file === 'broken.yaml')?.error).toBeTruthy();
  expect(() => validateLaunch(entry, { ...input, config: 'broken.yaml' })).toThrow();
});

test('the consensus-then-build workflow is held to the panel rules and the commit guard', () => {
  const entry = project();
  const models = ['omniroute/claude/claude-sonnet-5', 'omniroute/codex/gpt-5.6-luna-medium',
    'omniroute/cfp/moonshotai/kimi-k2.6'];
  // It builds and commits, so it needs explicit authorization like any SDLC.
  expect(() => validateLaunch(entry, { ...input, workflow: 'fusion-sdlc', models })).toThrow();
  // And it convenes a panel, so it needs a valid roster like any fusion run.
  expect(() => validateLaunch(entry, {
    ...input, workflow: 'fusion-sdlc', allow_changes: true, models: models.slice(0, 2),
  })).toThrow();
  expect(() => validateLaunch(entry, {
    ...input, workflow: 'fusion-sdlc', allow_changes: true, models,
  })).not.toThrow();
});

test('a roster linked to another served factory is usable, not an escape', () => {
  // `just init` links a project's rosters at the factory owning the shared
  // engine. Refusing every symlink left linked factories with no roster at all
  // — the launcher showed a project it could not run.
  const home = project();
  const linked = project();
  const shared = join(home.path, 'adws/adw_sssf_config/sssf.config.yaml');
  const here = join(linked.path, 'adws/adw_sssf_config/shared.yaml');
  symlinkSync(shared, here);

  // Without a trusted root the old, strict rule still holds.
  expect(() => projectOptions(linked)).toThrow('symlink escapes');

  // Served from a common root, the link is the supported layout.
  const trusting = { ...linked, trustedRoots: [linked.base, home.base] };
  const rosters = projectOptions(trusting).configs.map(item => item.file);
  expect(rosters).toContain('shared.yaml');
  expect(() => validateLaunch(trusting, { ...input, config: 'shared.yaml' })).not.toThrow();

  // A link out to somewhere nobody serves is still refused.
  const outside = join(linked.base, 'outside.yaml');
  writeFileSync(outside, 'defaults: {}');
  symlinkSync(outside, join(linked.path, 'adws/adw_sssf_config/outside.yaml'));
  expect(() => validateLaunch({ ...linked, trustedRoots: [join(linked.base, 'product')] },
    { ...input, config: 'outside.yaml' })).toThrow('symlink escapes');
});

test('a roster carries its composed Fusion panel to the launcher', () => {
  const entry = project();
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/sssf.config.yaml'),
    'defaults:\n  data_dir: adws/adw_data\n  model: omniroute/codex/gpt-5.6-sol-high\n' +
    'fusion:\n  panel:\n    - omniroute/codex/gpt-5.6-sol-high\n' +
    '    - omniroute/claude/claude-opus-5\n    - omniroute/codex/gpt-5.6-terra-high\n' +
    '  synthesizer: omniroute/codex/gpt-5.6-sol-high\n  openers: []\n');

  const roster = projectOptions(entry).configs.find(item => item.file === 'sssf.config.yaml')!;
  // Speaking order is the composition, so it must survive the round trip intact.
  expect(roster.panel).toEqual(['omniroute/codex/gpt-5.6-sol-high',
    'omniroute/claude/claude-opus-5', 'omniroute/codex/gpt-5.6-terra-high']);
  expect(roster.synthesizer).toBe('omniroute/codex/gpt-5.6-sol-high');
  expect(roster.openers).toEqual([]);
});

test('a roster with named panels resolves fusion.use, and other panels stay selectable', () => {
  const entry = project();
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/sssf.config.yaml'),
    'defaults:\n  data_dir: adws/adw_data\n  model: omniroute/codex/gpt-5.6-sol-high\n' +
    'fusion:\n  use: mixed\n  panels:\n' +
    '    mixed:\n      panel:\n        - omniroute/codex/gpt-5.6-sol-high\n' +
    '        - omniroute/claude/claude-opus-5\n        - omniroute/codex/gpt-5.6-terra-high\n' +
    '      synthesizer: omniroute/codex/gpt-5.6-sol-high\n      openers: []\n' +
    '    codex:\n      allow_single_family: true\n      panel:\n' +
    '        - omniroute/codex/gpt-5.6-sol-high\n        - omniroute/codex/gpt-5.6-terra-high\n' +
    '        - omniroute/codex/gpt-5.6-luna-high\n' +
    '      synthesizer: omniroute/codex/gpt-5.6-sol-high\n      openers: []\n');

  const roster = projectOptions(entry).configs.find(item => item.file === 'sssf.config.yaml')!;
  // The `default` panel/synthesizer/openers fields surface fusion.use's panel.
  expect(roster.selectedPanel).toBe('mixed');
  expect(roster.panel).toEqual(['omniroute/codex/gpt-5.6-sol-high',
    'omniroute/claude/claude-opus-5', 'omniroute/codex/gpt-5.6-terra-high']);
  // Every named panel remains reachable, including the one not selected by default.
  expect(Object.keys(roster.panels)).toEqual(['mixed', 'codex']);
  expect(roster.panels.codex.allowSingleFamily).toBe(true);
  expect(roster.panels.codex.panel).toEqual(['omniroute/codex/gpt-5.6-sol-high',
    'omniroute/codex/gpt-5.6-terra-high', 'omniroute/codex/gpt-5.6-luna-high']);
});

test('a launch may pick a named panel other than fusion.use', () => {
  const entry = project();
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/sssf.config.yaml'),
    'defaults:\n  data_dir: adws/adw_data\n  model: omniroute/codex/gpt-5.6-sol-high\n' +
    'fusion:\n  use: mixed\n  panels:\n' +
    '    mixed:\n      panel:\n        - omniroute/codex/gpt-5.6-sol-high\n' +
    '        - omniroute/claude/claude-opus-5\n        - omniroute/codex/gpt-5.6-terra-high\n' +
    '      synthesizer: omniroute/codex/gpt-5.6-sol-high\n      openers: []\n' +
    '    codex:\n      allow_single_family: true\n      panel:\n' +
    '        - omniroute/codex/gpt-5.6-sol-high\n        - omniroute/codex/gpt-5.6-terra-high\n' +
    '        - omniroute/codex/gpt-5.6-luna-high\n' +
    '      synthesizer: omniroute/codex/gpt-5.6-sol-high\n      openers: []\n');

  const { models: _omitted, ...withoutModels } = input;
  expect(() => validateLaunch(entry,
    { ...withoutModels, workflow: 'fusion', panel: 'codex' })).not.toThrow();
  expect(() => validateLaunch(entry,
    { ...withoutModels, workflow: 'fusion', panel: 'missing-panel' })).toThrow();
});

test('the simplified launcher omits models and gets the roster panel for free', async () => {
  const entry = project();
  writeFileSync(join(entry.path, 'adws/adw_sssf_config/sssf.config.yaml'),
    'defaults:\n  data_dir: adws/adw_data\n  model: omniroute/codex/gpt-5.6-sol-high\n' +
    'fusion:\n  panel:\n    - omniroute/codex/gpt-5.6-sol-high\n' +
    '    - omniroute/claude/claude-opus-5\n    - omniroute/codex/gpt-5.6-terra-high\n' +
    '  synthesizer: omniroute/codex/gpt-5.6-sol-high\n  openers: []\n');
  writeFileSync(join(entry.path, 'adws/adw_fusion_plan.py'),
    'import sys\nprint("argv:", sys.argv[1:], flush=True)\n');

  // No models field at all — not even an empty array — is the request shape
  // the simplified web form actually sends.
  const { models: _omitted, ...withoutModels } = input;
  expect(() => validateLaunch(entry, { ...withoutModels, workflow: 'fusion' })).not.toThrow();

  const started = await launch(entry, { ...withoutModels, workflow: 'fusion' });
  const state = await finished(entry, started.adw_id);
  expect(state.status).toBe('success');
  // The ADW resolves its own panel from the roster; the web server never
  // passes --models when the caller named none, so there is exactly one
  // place a default panel is ever assembled.
  expect(state.output).not.toContain('--models');
});

test('omitting models refuses cleanly when the roster has no usable panel', () => {
  const entry = project();   // the fixture roster carries no fusion: block
  const { models: _omitted, ...withoutModels } = input;
  expect(() => validateLaunch(entry, { ...withoutModels, workflow: 'fusion' }))
    .toThrow('has no usable Fusion panel');
});

test('a roster with no fusion block reports an empty panel rather than failing', () => {
  const entry = project();
  const roster = projectOptions(entry).configs.find(item => item.file === 'sssf.config.yaml')!;
  expect(roster.panel).toEqual([]);
  expect(roster.synthesizer).toBe('');
});

test('operator boundary rejects cross-site, forged hosts and missing tokens', () => {
  expect(() => guardOperator(new Request('http://localhost:4600/api/operator'), 4600)).not.toThrow();
  for (const [url, headers] of [
    ['http://evil.invalid:4600/api/operator', {}],
    ['http://localhost:4600/api/operator', { origin: 'https://evil.invalid' }],
    ['http://localhost:4600/api/operator', { origin: 'null' }],
    ['http://localhost:4600/api/operator', { 'sec-fetch-site': 'cross-site' }],
  ] as [string, Record<string, string>][]) {
    expect(() => guardOperator(new Request(url, { headers }), 4600)).toThrow();
  }
  expect(() => guardOperator(new Request('http://localhost:4600/api/launch', { method: 'POST' }), 4600, true)).toThrow();
  expect(() => guardOperator(new Request('http://localhost:4600/api/launch', { method: 'POST',
    headers: { 'x-sssf-token': operatorToken, origin: 'http://localhost:4601' } }), 4600, true)).not.toThrow();
});

const tailnetLaunch = (headers: Record<string, string>) => new Request(
  'http://factory.tail1234.ts.net:4600/api/launch', { method: 'POST', headers });

test('SSSF_TRUSTED_HOSTS widens the fence to named authorities and nothing else', () => {
  const restore = process.env.SSSF_TRUSTED_HOSTS;
  process.env.SSSF_TRUSTED_HOSTS = ' factory.tail1234.ts.net , box.example:4600 ';
  try {
    // A listed authority is reachable, by bare name and by host:port.
    expect(() => guardOperator(new Request('http://factory.tail1234.ts.net:4600/api/operator'), 4600)).not.toThrow();
    expect(() => guardOperator(new Request('http://box.example:4600/api/operator'), 4600)).not.toThrow();
    // Reachability only: a write from one still needs the operator token.
    expect(() => guardOperator(tailnetLaunch({}), 4600, true)).toThrow();
    expect(() => guardOperator(tailnetLaunch({ 'x-sssf-token': operatorToken }), 4600, true)).not.toThrow();
    // Everything unlisted stays refused, including a sibling name and a wrong port.
    for (const url of ['http://evil.invalid:4600/api/operator',
      'http://other.tail1234.ts.net:4600/api/operator', 'http://box.example:4700/api/operator']) {
      expect(() => guardOperator(new Request(url), 4600)).toThrow();
    }
    expect(() => guardOperator(new Request('http://factory.tail1234.ts.net:4600/api/operator',
      { headers: { origin: 'https://evil.invalid' } }), 4600)).toThrow();
  } finally {
    if (restore === undefined) delete process.env.SSSF_TRUSTED_HOSTS;
    else process.env.SSSF_TRUSTED_HOSTS = restore;
  }
  // Unset again, the same tailnet name is refused: the fence is loopback-only by default.
  expect(() => guardOperator(new Request('http://factory.tail1234.ts.net:4600/api/operator'), 4600)).toThrow();
});

test('launch validation rejects path escapes, unimplemented runtimes, weak quorum and unconfirmed writes', async () => {
  const entry = project();
  for (const change of [{ config: '../../elsewhere.yaml' }, { workflow: '../shell' }, { runtime: 'deepseek' },
    { prompt: '' }, { prompt: 'x'.repeat(32001) }, { workflow: 'sdlc' },
    { workflow: 'fusion', models: ['a/one', 'a/two'] }]) {
    expect(() => validateLaunch(entry, { ...input, ...change })).toThrow();
  }
  await expect(launch(entry, { ...input, workflow: 'sdlc', allow_changes: true })).rejects.toThrow('Commit or stash');
  const external = join(entry.base, 'external.yaml');
  writeFileSync(external, 'defaults: {}');
  symlinkSync(external, join(entry.path, 'adws/adw_sssf_config/escape.yaml'));
  expect(() => validateLaunch(entry, { ...input, config: 'escape.yaml' })).toThrow('symlink escapes');
});

test('real argv launch preserves literal request text and captures startup failures', async () => {
  const entry = project("import pathlib, sys\nprint(pathlib.Path(sys.argv[1]).read_text(), flush=True)\nsys.exit(7)\n");
  const prompt = 'do not execute $(touch ESCAPED); --config /outside';
  const started = await launch(entry, { ...input, prompt });
  const state = await finished(entry, started.adw_id);
  expect(state.status).toBe('fail');
  expect(state.exit_code).toBe(7);
  expect(state.output).toContain(prompt);
  expect(readFileSync(join(entry.path, 'adws/adw_data/sessions', started.adw_id, 'web_request.md'), 'utf8')).toBe(prompt);
  expect(projectOptions(entry).web_runs[0].adw_id).toBe(started.adw_id);
}, 10000);

test('Fusion requires at least two families; versions and routing providers are not families', () => {
  const entry = project();
  const models = ['openai-codex/gpt-5.6-luna', 'google/gemini-3.1-pro-preview', 'openrouter/anthropic/claude-sonnet-4-6'];
  const routed = ['omniroute/fusion-ovh/gpt-oss-20b', 'omniroute/fusion-kilo/nvidia/nemotron-3.5-lightning:free',
    'omniroute/zai/glm-5.2', 'omniroute/moonshot/kimi-k2', 'omniroute/anthropic/claude-sonnet-4-6'];
  const free = ['openrouter/nvidia/nemotron-3.5-lightning:free',
    'openrouter/inclusionai/ling-3.0-flash-fin:free', 'openrouter/cohere/north-mini-code:free'];
  for (const roster of [models, [...models, 'xai/grok-4'], routed, free,
    // Two Geminis are one family — but with Claude alongside, the floor is met.
    [models[1], 'router/google/gemini-2.5-pro', models[2]],
    [...models, 'xai/grok-4', 'xai/grok-3'],
    // Ten models drawn from four families: a big panel, not an echo chamber.
    ['omniroute/anthropic/claude-sonnet-4-6', 'omniroute/anthropic/claude-opus-4-6',
      'omniroute/anthropic/claude-haiku-4-5', 'openai-codex/gpt-5.6-luna',
      'openai-codex/gpt-5.6-sol', 'openai-codex/gpt-5.6-terra', 'omniroute/zai/glm-5.2',
      'omniroute/zai/glm-4.7-flash', 'omniroute/moonshot/kimi-k2', 'omniroute/moonshot/kimi-k1'],
    [...routed, 'google/gemini-3.1-pro-preview'],
  ]) {
    expect(() => validateLaunch(entry, { ...input, workflow: 'fusion', models: roster })).not.toThrow();
  }
  for (const roster of [
    [models[0], models[1], 'anthropic/claude-sonnet-4-6'],          // Claude must ride OpenRouter/OmniRoute
    [models[0], 'openai-codex/gpt-5.6-terra', 'openai-codex/gpt-5.6-sol'], // one family is an echo, not a panel
    [models[0], models[2], 'router/anthropic/claude-opus-4-6'],     // Claude on an unapproved router
    [models[0], models[1], 'custom/unknown'],                       // unrecognized family
    [models[0], models[0], models[1]],                              // a model may not hold two seats
  ]) {
    expect(() => validateLaunch(entry, { ...input, workflow: 'fusion', models: roster })).toThrow('at least two families');
  }
});

test('the synthesizer must be one of the discussion models', () => {
  const entry = project();
  const models = ['openai-codex/gpt-5.6-luna', 'google/gemini-3.1-pro-preview', 'openrouter/anthropic/claude-sonnet-4-6'];
  expect(() => validateLaunch(entry, { ...input, workflow: 'fusion', models })).not.toThrow();
  expect(() => validateLaunch(entry, { ...input, workflow: 'fusion', models, synthesizer: models[1] })).not.toThrow();
  for (const synthesizer of ['openai-codex/gpt-5.6-terra', 42 as unknown as string]) {
    expect(() => validateLaunch(entry, { ...input, workflow: 'fusion', models, synthesizer })).toThrow('synthesizer');
  }
});

test('one live web run per project, cancellable as its own process group', async () => {
  const entry = project("import time\nprint('waiting', flush=True)\ntime.sleep(30)\n");
  const started = await launch(entry, input);
  try {
    await expect(launch(entry, input)).rejects.toThrow('already has a web launch');
    expect(stop(entry, started.adw_id).status).toBe('stopping');
    expect((await finished(entry, started.adw_id)).status).toBe('cancelled');
  } finally {
    if (['running', 'stopping'].includes(webRun(entry, started.adw_id)!.status)) stop(entry, started.adw_id);
  }
}, 10000);

test('dead persisted launcher is marked interrupted, never success', () => {
  const entry = project();
  const id = 'web-1234567890abcdef';
  const dir = join(entry.path, 'adws/adw_data/sessions', id);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'web_launch.json'), JSON.stringify({ adw_id: id, status: 'running',
    pid: 2147483647, start_ticks: 'not-a-real-process', started_at: new Date().toISOString() }));
  writeFileSync(join(entry.path, 'adws/adw_data/sessions/.web-run.lock'), id);
  expect(webRun(entry, id)?.status).toBe('interrupted');
});
