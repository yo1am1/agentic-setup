/** Family comes from the model ID, not the provider carrying it. */
export function modelFamily(model: string): string | undefined {
  const identity = model.split('/').at(-1)!.toLowerCase();
  if (identity.startsWith('gpt-')) return 'openai';
  // Mirrors model_family() in adw_modules/fusion.py — a family missing here and
  // present there makes the launcher refuse a panel the CLI runs happily.
  return ['gemini', 'grok', 'claude', 'kimi', 'glm', 'deepseek', 'nemotron', 'laguna',
          'north', 'ling', 'mimo', 'qwen', 'nex', 'inkling']
    .find(family => identity.startsWith(`${family}-`));
}

export function allowedFusionModel(model: string): boolean {
  const family = modelFamily(model);
  return family !== undefined && (family !== 'claude' || ['openrouter', 'omniroute'].includes(model.split('/')[0]!));
}

export const MIN_PANEL = 3;
export const MAX_PANEL = 12;
/**
 * Diversity floor. Two families is the honest minimum: on a given machine only
 * a couple of vendors are usually reachable AND able to follow a strict
 * contract for a whole debate. One family is an echo, not a panel.
 * Mirrors MIN_CORE_FAMILIES in adw_modules/fusion.py.
 */
export const MIN_FAMILIES = 2;

export function validFusionModels(models: string[]): boolean {
  const families = new Set(models.map(modelFamily));
  return models.length >= MIN_PANEL && models.length <= MAX_PANEL
    && new Set(models).size === models.length
    && models.every(allowedFusionModel)
    && families.size >= MIN_FAMILIES;
}

/**
 * The synthesizer turns the debate into the plan, so it must be a voice that
 * debated: a panel member, never an outside model. Mirrors configure() in
 * adw_modules/fusion.py. The order of `models` is the speaking order.
 */
export function validFusionSynthesizer(synthesizer: string, models: string[]): boolean {
  return models.includes(synthesizer);
}

/** Workflow ids that convene a model panel and therefore require a roster. */
export const FUSION_FLOWS = new Set(['fusion', 'fusion-sdlc']);
