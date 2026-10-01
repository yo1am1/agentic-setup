"""Small protocol helpers for the optional Fusion planning ADW."""

import json
import os
import tempfile
import time
from concurrent import futures

from . import agent_pi, agents, utils
from .data_types import AgentConfig, GateReport, PromptEngineering

# Substrings of provider errors that describe the transport, not the agent: a
# free model rate-limiting, a browser-backed bridge dropping its stream, a
# gateway hiccup. A debate roster deliberately mixes reliable subscription
# models with unreliable free ones, so these are expected, not exceptional.
TRANSIENT_PROVIDER_ERRORS = (
    "cooling down", "stream_early_eof", "rate limit", "429",
    "502", "503", "504", "timed out", "timeout",
)

PROMPTS = "adws/adw_data/prompt_engineering/fusion"
# Semantic search for the seats: one graphify_query call replaces the
# grep→read→grep chains that used to eat the evidence budget. The tool is
# read-only and degrades to "use grep/find" when the repo has no index.
GRAPHIFY = "adws/adw_data/harness_engineering/graphify_query.ts"

# Below this many surviving participants a debate is no longer a panel, so a run
# that has lost too many models stops instead of quietly calling two models a
# consensus. Dropouts above the floor are recorded, never hidden.
MIN_PANEL = 3
# Diversity floor. Two families is the honest minimum: on a given machine only a
# couple of vendors are usually reachable AND able to follow a strict contract
# for a whole debate, so demanding more bans the only panels that actually run.
# One family is still an echo rather than a panel, and stays rejected.
MIN_FAMILIES = 2
MIN_CORE_FAMILIES = 2
# A ceiling on the panel: every extra model is two more opinion phases plus a
# vote, so an unbounded roster is an unbounded runtime even fanned out.
MAX_PANEL = 12
# How many seats may hold a turn at once. Every fan-out in the protocol is
# already a barrier — round 1 is independent by definition, round 2 critiques
# the *frozen* round-1 set, and a vote reads one hash-pinned plan — so seats
# never needed to take turns; they only did because the tracer, the phase
# counter and the checkpoint were single-threaded (see the note this replaces
# in adw_fusion_plan). Sequentially a round costs the sum of its seats; fanned
# out it costs the slowest one, which is what makes a six-seat panel affordable.
#
# The ceiling exists because OmniRoute admits a bounded number of heavy chat
# turns concurrently: `OMNIROUTE_CHAT_MAX_HEAVY_IN_FLIGHT`, whose **default is
# 1**, and whose excess arrivals get `503 chat_admission_busy` once the
# admission queue drains. 6 matches the value this engine documents; a factory
# whose gateway runs the default must set SSSF_FUSION_CONCURRENCY=1.
MAX_PARALLEL = 6


# Vendors whose models reason differently enough to argue rather than echo. A
# model whose ID matches none of these is refused from a panel outright — an
# unclassifiable seat cannot be counted toward the diversity floor. Mirrored in
# the visualizer's shared/fusion.ts and pinned by a test, because a family
# known to only one side makes the launcher refuse a panel the CLI runs.
FAMILIES = ("gemini", "grok", "claude", "kimi", "glm", "deepseek", "nemotron",
            "laguna", "north", "ling", "mimo", "qwen", "nex", "inkling")


def model_family(model: str) -> str | None:
    """Classify the resolved model ID, not its provider or routing alias."""
    identity = model.rsplit("/", 1)[-1].lower()
    if identity.startswith("gpt-"):
        return "openai"
    return next((family for family in FAMILIES
                 if identity.startswith(family + "-")), None)


def with_defaults(cfg, models, openers, synthesizer_model, panel_name=None):
    """Use an explicit panel, a named YAML panel, or the roster default.

    A named panel may set `allow_external_synthesizer: true` to name a
    "collector" model that never debates or votes — it only turns the
    frozen debate into the plan. That model is deliberately NOT required to
    be a panel member here; `configure()` is the single place that enforces
    membership, gated on that same flag, so this function must not silently
    drop the configured synthesizer before configure() ever sees it.
    """
    selected = cfg.fusion
    if models is None:
        name = panel_name or cfg.fusion.use
        if name != "default":
            if name not in cfg.fusion.panels:
                raise ValueError(f"unknown Fusion panel {name!r}; available: "
                                 f"{['default', *cfg.fusion.panels]}")
            selected = cfg.fusion.panels[name]
    panel = list(models) if models is not None else list(selected.panel)
    voices = list(openers) if openers is not None else list(selected.openers)
    chosen = synthesizer_model or (selected.synthesizer or None)
    external_ok = models is None and selected.allow_external_synthesizer
    if chosen and chosen not in panel and not external_ok:
        chosen = None
    return panel, voices, chosen


def allow_single_family(cfg, models, panel_name=None):
    if models is not None:
        return False
    name = panel_name or cfg.fusion.use
    if name == "default":
        return cfg.fusion.allow_single_family
    return cfg.fusion.panels[name].allow_single_family


def panel_thinking(cfg, models, panel_name=None):
    if models is not None:
        return None
    name = panel_name or cfg.fusion.use
    selected = cfg.fusion if name == "default" else cfg.fusion.panels[name]
    return selected.seat_thinking or None


def allow_external_synthesizer(cfg, models, panel_name=None):
    if models is not None:
        return False
    name = panel_name or cfg.fusion.use
    selected = cfg.fusion if name == "default" else cfg.fusion.panels[name]
    return selected.allow_external_synthesizer


def configure(cfg, models: list[str], openers: list[str] | None = None,
              tag: str | None = None, synthesizer_model: str | None = None,
              allow_single_family: bool = False, thinking: list[str] | None = None,
              allow_external_synthesizer: bool = False):
    """Create fresh read-only slots; never modify the engineer's saved roster.

    `models` is the core panel: it debates every round, votes, and supplies the
    synthesizer. Speaking order is the order given. `synthesizer_model` names
    the panel member that turns the debate into the plan (default: the first
    model) — it must be a core member, because the model that ratifies the plan
    should be one that also debated it. `openers` are opening-round-only voices
    — models worth hearing a first position from but unable to carry the
    protocol, because their context is too small for a round of peer proposals
    or their quota is too thin to survive one. They propose, they are argued
    with, they never vote.
    """
    openers = list(openers or [])
    everyone = [*models, *openers]
    error = (f"Fusion requires a core panel of {MIN_PANEL}–{MAX_PANEL} distinct models with at "
             f"least {MIN_CORE_FAMILIES} families, and at least {MIN_FAMILIES} families across "
             "the opening round: OpenAI, Gemini, Grok, Claude, Kimi, GLM, Nemotron, Laguna, "
             "North, Ling")
    if not MIN_PANEL <= len(models) <= MAX_PANEL or len(set(everyone)) != len(everyone):
        raise ValueError(error)
    models = ["/".join(agent_pi.resolve_model(model)) for model in models]
    openers = ["/".join(agent_pi.resolve_model(model)) for model in openers]
    everyone = [*models, *openers]
    families = [model_family(model) for model in everyone]
    core_families = {model_family(model) for model in models}
    if (None in families or len(set(everyone)) != len(everyone)
            or (not allow_single_family and
                (len(set(families)) < MIN_FAMILIES
                 or len(core_families) < MIN_CORE_FAMILIES))):
        if not allow_single_family:
            error += "; named YAML panels may opt in with allow_single_family: true"
        raise ValueError(error)
    if any(family == "claude" and model.split("/", 1)[0] not in {"openrouter", "omniroute"}
           for model, family in zip(everyone, families, strict=True)):
        raise ValueError("Claude in Fusion must use OpenRouter or OmniRoute, not direct Anthropic")
    synthesis_model = (models[0] if synthesizer_model is None
                       else "/".join(agent_pi.resolve_model(synthesizer_model)))
    if synthesis_model not in models and not allow_external_synthesizer:
        raise ValueError("The synthesizer must be a member of the core panel: the model that "
                         "writes the plan must be one that also debated and votes on it")
    tag = tag or utils.new_id(8)
    participants = [f"fusion_{i}_{tag}" for i in range(1, len(models) + 1)]
    opening = [f"opening_{i}_{tag}" for i in range(1, len(openers) + 1)]
    synthesizer = f"fusion_synthesis_{tag}"
    efforts = list(thinking or [])
    for index, (name, model) in enumerate(zip([*participants, *opening, synthesizer],
                                               [*models, *openers, synthesis_model], strict=True)):
        effort = (efforts[index] if index < len(efforts)
                  else cfg.fusion.thinking.synthesis if name == synthesizer
                  else cfg.fusion.thinking.opinion)
        # Effort is per STEP, not per seat (see FusionThinking): synthesis reads
        # both full rounds from every participant and turns the disagreement
        # into the one implementable plan, so it never inherits the everyday
        # default. Voting is re-tuned at its own call site, where the seat's
        # prompt is swapped for vote.md.
        #
        # The synthesizer gets NO TOOLS, and that is the whole point of the
        # seat. Its input — both full rounds from every participant, with the
        # file:line evidence they already gathered — is handed to it inline in
        # `previous`, so a tool is never how it learns anything; it is only how
        # it becomes a fourth investigator. Given the seats' tool set it behaved
        # exactly like one: 74 tool calls, `operator.ts` read 20 times,
        # `index.ts` grepped 9 times, 94 minutes and 3.47M tokens for one plan —
        # 77% of that run's entire cost, more tool calls than any seat that was
        # actually supposed to investigate. Aggregating proposals is a
        # text-to-text step (the aggregator layer in Mixture-of-Agents, the
        # judge in multi-agent debate); re-deriving the problem is both the
        # expensive failure and the one that quietly discards the debate.
        aggregating = name == synthesizer
        cfg.agents.append(AgentConfig(
            name=name, model=model,
            thinking=effort,
            purpose="Read-only Fusion planning; no implementation or commits",
            prompt_engineering=PromptEngineering(system=f"{PROMPTS}/system.md",
                user=f"{PROMPTS}/{'synthesis' if aggregating else 'opinion'}.md"),
            tools=[] if aggregating else ["read", "grep", "find", "ls", "graphify_query"],
            writes=[],
            harness_engineering=[] if aggregating else [GRAPHIFY]))
    agents.validate(cfg, [*participants, *opening, synthesizer])
    return participants, opening, synthesizer, tag


def concurrency(seats: int) -> int:
    """How many of `seats` may run at once: the gateway's ceiling, or 1.

    `SSSF_FUSION_CONCURRENCY` is the escape hatch in both directions — 1 on a
    gateway left at its single-slot default, higher on one configured for it.
    A value that is not a positive integer is ignored rather than obeyed: this
    decides how hard a run leans on a shared gateway, and a typo should not.
    """
    limit = MAX_PARALLEL
    configured = os.environ.get("SSSF_FUSION_CONCURRENCY", "").strip()
    if configured.isdigit() and int(configured) > 0:
        limit = int(configured)
    return max(1, min(seats, limit))


def parallel_safe(cfg, names: list[str]) -> bool:
    """True when these seats may share a round, checked rather than assumed.

    Read-only is the precondition for the whole fan-out. `permissions.enforce`
    brackets every agent call with a snapshot of the working tree and rolls
    back whatever falls outside that agent's allowlist; run concurrently, the
    snapshots interleave and blame lands on whichever seat happened to finish
    around the change. With every participant at `writes: []` the allowlist is
    empty for all of them, so the set of paths rolled back is identical either
    way and only the name in the error message is affected — which is a price
    worth paying. With a writing seat it is not, and this returns False so the
    caller stays sequential instead.
    """
    return all(agents.resolve(cfg, name).writes == [] for name in names)


def in_parallel(cfg, names: list[str], work) -> dict:
    """Run `work(name)` for each seat, bounded, and return {name: result}.

    Results are keyed, never ordered by completion: the debate record has to
    read the same way whichever seat answers first, or a rerun of the same
    panel produces a different-looking round.

    The first exception is re-raised once every thread has stopped, so a failed
    seat cannot leave siblings writing into a run that is already unwinding —
    and because each accepted answer is checkpointed as it lands, the ones that
    did finish are still there for `--resume`.
    """
    if len(names) < 2 or not parallel_safe(cfg, names):
        return {name: work(name) for name in names}
    results: dict = {}
    with futures.ThreadPoolExecutor(max_workers=concurrency(len(names)),
                                    thread_name_prefix="fusion") as pool:
        pending = {pool.submit(work, name): name for name in names}
        for future in futures.as_completed(pending):
            results[pending[future]] = future.result()
    return {name: results[name] for name in names}


def save(path, value) -> str:
    # A killed writer must leave the previous checkpoint intact, never half a JSON file.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(json.dumps(value, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return str(path)


def reviewed_exact_plan(digest: str):
    def plan_hash_matches(vote, _run):
        return GateReport().check("plan_sha256", vote.plan_sha256 == digest,
                                   "vote must name the exact supplied plan hash")
    return plan_hash_matches


def transient(error: Exception) -> bool:
    """True when the failure is the provider's transport, not the agent's answer."""
    # GateFailure and PermissionBreach also inherit RuntimeError. Never mask them
    # because a file, test name or model answer happens to contain "429"/"timeout".
    if type(error) is not RuntimeError:
        return False
    message = str(error).lower()
    return any(marker in message for marker in TRANSIENT_PROVIDER_ERRORS)


# ONE extra turn, not a ladder. Every attempt here re-runs the participant's
# whole investigation from zero — one measured seat spent 615k tokens and 49
# turns before answering, so a third attempt costs more than most failures are
# worth. Two other layers already retry underneath this one without repeating
# any of that work: pi retries the failed request in-session (2s/4s/8s), and
# OmniRoute queues, cools down and falls back upstream. This layer exists only
# for what neither can reach — a pi process that died with nothing produced.
RETRY_ATTEMPTS = 2


def call_with_retry(run, params, call, attempts: int = RETRY_ATTEMPTS, sleep=None):
    """Give a flaky participant one more turn before killing a long debate.

    One participant's provider failing must not discard the other nine models'
    completed work. Each attempt is its own phase, so a retry is visible in the
    trace instead of hidden inside one. A non-transient failure — a real gate
    violation, a broken contract — still aborts immediately, and so does a
    participant that never recovers: a quorum that silently shrinks would
    manufacture consensus out of absence.
    """
    for attempt in range(1, attempts + 1):
        try:
            # Every attempt but the last may still be rescued, so it must not
            # close the session out from under the attempts that follow it.
            with run.phase(params.model_copy(update={"recoverable": params.recoverable or attempt < attempts})) as phase:
                return phase.call(call)
        except RuntimeError as error:
            if attempt == attempts or not transient(error):
                raise
            run.console.note(f"{params.name}: transient provider failure, retrying "
                             f"({attempt}/{attempts - 1}) — {error}")
            (sleep or time.sleep)(min(60, 20 * attempt))
