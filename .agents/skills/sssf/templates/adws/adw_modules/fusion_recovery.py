"""Durable checkpoints for read-only Fusion calls, not for SDLC side effects."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import agents, fusion, git_helper, utils


@dataclass
class RecoveryOptions:
    resume: bool = False
    fallback_models: list[str] = field(default_factory=list)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def model_identity(model: str) -> str:
    # Thinking variants and alternate routers are not extra independent voters.
    return re.sub(r"-(?:low|medium|high|xhigh|max|ultra)$", "", model.rsplit("/", 1)[-1].lower())


def repository_digest(root: Path) -> str:
    """Include dirty/untracked source too; HEAD alone cannot validate old evidence."""
    paths = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True).stdout.split(b"\0")
    result = hashlib.sha256()
    for name in sorted(set(paths) - {b""}):
        path = root / os.fsdecode(name)
        result.update(name + b"\0")
        if path.is_symlink():
            result.update(b"link:" + os.fsencode(os.readlink(path)))
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    result.update(chunk)
        else:
            result.update(b"missing")
        result.update(b"\0")
    return result.hexdigest()


class Checkpoint:
    def __init__(self, run, cfg, options: RecoveryOptions):
        self.run, self.cfg, self.options = run, cfg, options
        self.path = run.context_handoff_dir / "fusion_checkpoint.json"
        self.lock = None
        # `self.lock` is the inter-process flock on the checkpoint file. This is
        # the in-process one: a parallel round has every seat recording its own
        # completed step into the same `state["steps"]` dict and rewriting the
        # same file, and a half-written checkpoint is one that refuses --resume.
        self._lock = threading.RLock()

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError("This Fusion checkpoint is already in use") from None
        return self

    def __exit__(self, *_):
        self.lock.close()

    def prepare(self, prompt, models, openers, synthesizer_model=None):
        # Never store the whole config: it may contain credentials.
        identity = digest(dict(prompt=prompt, models=models, openers=openers or [],
                               synthesizer_model=synthesizer_model,
                               config=self.cfg.model_dump(mode="json"),
                               repository=repository_digest(git_helper.repo_root()),
                               protocol=digest({p.name: p.read_text() for p in
                                   [*Path(__file__).parent.glob("*.py"),
                                    Path(__file__).parent.parent / "adw_fusion_plan.py"]})))
        if self.options.resume:
            if not self.path.exists():
                raise ValueError("No Fusion checkpoint exists for this session; legacy runs cannot be auto-resumed")
            self.state = json.loads(self.path.read_text())
            if self.state.get("version") != 1 or self.state.get("identity") != identity:
                raise ValueError("Checkpoint inputs or repository changed; use a new --adw-id")
            if self.state.get("implementation_started"):
                raise ValueError("SDLC implementation already started; Fusion resume cannot replay code changes or commits")
        else:
            if self.path.exists():
                raise ValueError("Fusion checkpoint already exists; use --resume or a new --adw-id")
            self.state = dict(version=1, identity=identity, tag=utils.new_id(8),
                              steps={}, models={}, substitutions=[], status="running")
        self.fallbacks = ["/".join(fusion.agent_pi.resolve_model(m)) for m in self.options.fallback_models]
        for model in self.fallbacks:
            if fusion.model_family(model) is None or (fusion.model_family(model) == "claude"
                    and model.split("/", 1)[0] not in {"openrouter", "omniroute"}):
                raise ValueError(f"Unsupported Fusion fallback: {model}")
        self.state["status"] = "running"
        self.save()
        return self.state["tag"]

    def bind(self, names):
        self.names = names
        for name in names:
            agent = agents.resolve(self.cfg, name)
            agent.model = self.state["models"].setdefault(name, agent.model)
        seats = [model_identity(self.state["models"][n]) for n in names if not n.startswith("fusion_synthesis_")]
        if len(set(seats)) != len(seats):
            raise ValueError("Fusion seats must use distinct models, not alternate routers or thinking variants")
        # Reserves must not be another seat already voting in this panel.
        original = {entry["from"] for entry in self.state["substitutions"]}
        self.used = {model_identity(m) for m in set(self.state["models"].values()) | original}
        self.save()

    def save(self):
        with self._lock:
            fusion.save(self.path, self.state)

    def call(self, params, call):
        key = params.name
        inputs = digest(dict(prompt=call.prompt, previous=call.previous.model_dump() if call.previous else None,
                             output=call.output_type.__name__))
        saved = self.state["steps"].get(key)
        if saved is not None:
            if saved["inputs"] != inputs or saved["sha256"] != digest(saved["output"]):
                raise ValueError(f"Checkpoint mismatch at {key}; refusing stale results")
            result = call.output_type.model_validate(saved["output"])
            self.validate(result, call)
            # A visible zero-model-call phase also lets an entirely cached run finish normally.
            with self.run.phase(params) as phase:
                phase.log(checkpoint_reused=key, model=saved["model"], checkpoint=str(self.path))
            return result

        agent = agents.resolve(self.cfg, params.owner)
        while True:
            try:
                outgoing = call
                if call.previous is not None and any(s["slot"] == params.owner for s in self.state["substitutions"]):
                    own = [v["output"] for k, v in self.state["steps"].items() if k.endswith("_" + params.owner)]
                    outgoing = call.model_copy(update={"previous": call.previous.model_copy(update={
                        "notes_for_next_agent": call.previous.notes_for_next_agent
                        + "\nThis slot had a model replacement. Its accepted outputs:\n" + json.dumps(own)})})
                # All attempts here are handled by this checkpoint, not by the phase finalizer.
                result = fusion.call_with_retry(self.run, params.model_copy(update={"recoverable": True}), outgoing)
                self.validate(result, call)
                # Mutate and persist under the same lock: `save` serialises the
                # whole state, so a sibling seat recording its own answer
                # mid-write is a torn checkpoint, and a torn checkpoint is one
                # that refuses --resume.
                with self._lock:
                    self.state["steps"][key] = dict(inputs=inputs, model=agent.model,
                        output=result.model_dump(), sha256=digest(result.model_dump()))
                    # Clear only *this* step's block. Unscoped, a seat finishing
                    # normally erased the block a sibling had just recorded, and
                    # the run died reporting no blocked step at all — the first
                    # thing a parallel round broke.
                    if self.state.get("blocked_step") == key:
                        self.state.pop("blocked_step")
                    self.save()  # commit each accepted answer before another model starts
                return result
            except RuntimeError as error:
                with self._lock:
                    self.state.update(status="blocked", blocked_step=key)
                    self.save()
                if not fusion.transient(error):
                    raise
                replacement = next((m for m in self.fallbacks if model_identity(m) not in self.used
                                    and fusion.model_family(m) == fusion.model_family(agent.model)), None)
                if replacement is None:
                    self.run.console.note(f"Saved progress at {key}. Retry with the same arguments and --resume. "
                                          "No unused same-family fallback is available.")
                    raise
                change = dict(step=key, slot=params.owner, **{"from": agent.model, "to": replacement})
                self.state["substitutions"].append(change)
                self.used.add(model_identity(replacement))
                agent.model = replacement
                self.state["models"][params.owner] = replacement
                self.state["status"] = "running"
                self.save()
                with self.run.phase(params.model_copy(update={"name": f"fallback_{key}", "kind": "code"})) as phase:
                    phase.log(substitution=change, reason="transient provider failure")

    def validate(self, result, call):
        if result.status != "success":
            raise agents.GateFailure("Checkpoint only accepts successful envelopes")
        for gate in call.gates:
            if not agents._as_report(gate(result, self.run)).passed:
                raise agents.GateFailure("Checkpoint envelope failed its original gate")
