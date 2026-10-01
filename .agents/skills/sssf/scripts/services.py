#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Run OmniRoute, the Software Factory web app, the dsh web UI and SSLF as user services.

`just go` reduces to `services.py up`. Every surface, one command. For the
tailnet surfaces the interesting part is not starting them — it is that all are
reached the same way from a phone and none may be reached by anything else:

  * all stay bound to loopback; Tailscale Serve proxies the tailnet to them,
    so nothing is offered to the LAN and Funnel is never involved;
  * each has its own Host-header fence that must name every tailnet authority,
    and `tailnet-authorities.sh` is the single place that list comes from;
  * the units resolve that list at every start, so a changed Tailscale IP or
    MagicDNS name needs no edit anywhere.

With Tailscale down everything still starts, loopback-only. That is the same
code path, not a fallback: the authority script prints nothing, every fence stays
closed to everything but localhost, and `up` says so.

SSLF (the life factory, in its own checkout) is two units: its web app is
published like the others, and its API is not published at all — the web app
proxies same-origin `/api` to it on loopback, so one tailnet port serves both.

OmniRoute is the LLM gateway dsh and every SSSF phase call. It was hand-started
with `npx omniroute` and died with the terminal, which left dsh up and every model
call failing; as a unit it survives both. It has no Host fence of its own —
its dashboard login is the gate — so there is no allowlist to keep fresh.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
VISUALIZER = SKILL / "apps" / "visualizer"
AUTHORITIES = SKILL / "scripts" / "tailnet-authorities.sh"
UNIT_TEMPLATES = SKILL / "templates" / "systemd"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
DSH_CLI = Path.home() / ".dsh/profiles/node_modules/@deepseek-ai/dsh/lib/bin.js"
DSH_SHIM = Path.home() / ".local" / "bin" / "dsh"
DSH_PRESET_SOURCE = SKILL / "templates" / "dsh-preset"
DSH_PRESET_LINK = Path.home() / ".dsh" / ".agent-presets" / "sssf"
VISUALIZER_UNIT = "sssf-visualizer"
DSH_UNIT = "dsh-web"
SSLF_API_UNIT = "sslf-api"
SSLF_WEB_UNIT = "sslf-web"
OMNIROUTE_UNIT = "omniroute"
# Units `rebuild` produces new output for. Restarting the others on a rebuild
# would only cut off an open dsh session or in-flight LLM calls.
REBUILT_UNITS = (VISUALIZER_UNIT, SSLF_API_UNIT, SSLF_WEB_UNIT)


@dataclass(frozen=True)
class Surface:
    """One served app: its unit, its port, what to call it, and how to know it.

    `owns` holds substrings that identify this app in a process command line.
    They are what lets an unmanaged copy be replaced without ever touching an
    unrelated program that happens to hold the port.
    """

    unit: str
    port: int
    label: str
    owns: tuple[str, ...]
    tailnet: bool = True
    host_fence: bool = True


def visualizer_port() -> int:
    return int(os.environ.get("PORT", "4600"))


def dsh_port() -> int:
    return int(os.environ.get("DSH_WEB_PORT", "3080"))


def sslf_root() -> Path:
    return Path(os.environ.get("SSLF_ROOT", str(Path.home() / "VS" / "factories" / "sslf")))


def sslf_api_port() -> int:
    # Not PORT: that name already belongs to the visualizer in this process.
    return int(os.environ.get("SSLF_API_PORT", "3001"))


def sslf_web_port() -> int:
    return int(os.environ.get("SSLF_WEB_PORT", "5173"))


def omniroute_port() -> int:
    return int(os.environ.get("OMNIROUTE_PORT", "20128"))


def find_omniroute() -> Path:
    """Locate the OmniRoute CLI: OMNIROUTE_BIN, else the newest npx cache copy.

    Like dsh, it is not installed globally — `npx omniroute` put it in the npx
    cache, so a `npm cache clean` removes it. Refusing here with the remedy beats
    a unit that crash-loops at the next boot.
    """
    override = os.environ.get("OMNIROUTE_BIN")
    candidates = [Path(override)] if override else sorted(
        (Path.home() / ".npm/_npx").glob("*/node_modules/omniroute/bin/omniroute.mjs"),
        key=lambda path: path.stat().st_mtime)
    if not candidates or not candidates[-1].is_file():
        raise SystemExit(
            "OmniRoute CLI not found (set OMNIROUTE_BIN, or run `npx omniroute --version` "
            "once to fetch it), then run `just go` again.")
    return candidates[-1]


def surfaces() -> list[Surface]:
    root = sslf_root()
    # First, because dsh and every SSSF phase resolve models through it.
    return [Surface(OMNIROUTE_UNIT, omniroute_port(), "OmniRoute",
                    ("omniroute/bin/omniroute.mjs", "node_modules/omniroute/"),
                    host_fence=False),
            Surface(VISUALIZER_UNIT, visualizer_port(), "Software Factory",
                    ("server/index.ts",)),
            # A hand-started dsh is usually the npx cache copy, so the package
            # name identifies it where the shim path would not.
            Surface(DSH_UNIT, dsh_port(), "dsh web UI",
                    ("dsh/lib/bin.js", "dsh-web-app", "/.bin/dsh", "profile web")),
            # A hand-started SSLF is `npm run dev:*`, which runs tsx and vite
            # from this checkout's own node_modules — the root path is the mark.
            Surface(SSLF_API_UNIT, sslf_api_port(), "SSLF API",
                    (f"{root}/apps/api/", f"{root}/node_modules/.bin/tsx",
                     f"{root}/node_modules/tsx/"), tailnet=False),
            Surface(SSLF_WEB_UNIT, sslf_web_port(), "SSLF web",
                    (f"{root}/node_modules/.bin/vite", f"{root}/node_modules/vite/"))]


def require_sslf_build(root: Path) -> None:
    """Refuse before rendering units that could only crash-loop.

    The units run built output, so a missing checkout or an unbuilt one would
    otherwise surface as five fast restarts and a stopped unit in the journal.
    """
    for built in (root / "apps/api/dist/index.js", root / "apps/web/dist/index.html",
                  root / "node_modules/vite/bin/vite.js"):
        if not built.is_file():
            raise SystemExit(
                f"SSLF is not built: {built} is missing.\n"
                f"Set SSLF_ROOT if the checkout lives elsewhere (now {root}), "
                "then run `just go`, which installs and builds it first.")


def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command and capture it; the caller decides what a failure means."""
    return subprocess.run(argv, capture_output=True, text=True, check=False, **kwargs)  # type: ignore[arg-type]


def systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return run(["systemctl", "--user", *args])


def is_active(unit: str) -> bool:
    return systemctl("is-active", "--quiet", unit).returncode == 0


def require(name: str, *fallbacks: Path) -> Path:
    """Resolve an executable from PATH, else from a known install location."""
    found = shutil.which(name)
    if found:
        return Path(found)
    for candidate in fallbacks:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"{name} is required but was not found on PATH")


def unit_path_env(*executables: Path) -> str:
    """A PATH for the units: systemd user services inherit almost nothing."""
    seen: list[str] = []
    for entry in [*(str(path.parent) for path in executables),
                  str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"]:
        if entry not in seen:
            seen.append(entry)
    return ":".join(seen)


def install_dsh_shim(node: Path) -> Path:
    """dsh on PATH without a global npm install, via the profile's own CLI.

    Worth knowing where that actually points: the profile tree links
    `@deepseek-ai/dsh` into the npx cache under `~/.npm/_npx/`, so a
    `npm cache clean` takes the service with it. Resolving the link here turns
    that from a service that dies at the next boot into one refusal with the
    remedy in it. Rewritten every time, so an upgraded node never leaves the
    shim pointing at an interpreter that is gone.
    """
    if not DSH_CLI.resolve().is_file():
        raise SystemExit(
            f"the dsh CLI {DSH_CLI} does not resolve to a file "
            f"(it points at {DSH_CLI.resolve()}).\n"
            "Reinstall it — `npm install -g @deepseek-ai/dsh`, or re-run the "
            "npx command that created the profile — then run `just go` again.")
    DSH_SHIM.parent.mkdir(parents=True, exist_ok=True)
    DSH_SHIM.write_text(
        "#!/usr/bin/env bash\n"
        "# Written by services.py — dsh on PATH without a global npm install.\n"
        "# The link target is resolved, not followed at run time, so clearing\n"
        "# the npx cache fails here rather than deep inside the harness.\n"
        f'exec {node} {DSH_CLI.resolve()} "$@"\n')
    DSH_SHIM.chmod(0o755)
    return DSH_SHIM


def install_dsh_preset() -> bool:
    """Make the SSSF dsh preset a real, git-tracked artifact. Returns whether it changed.

    Before this, `~/.dsh/.agent-presets/sssf` was hand-authored on this one
    machine — not linked from here by anything, not covered by `just init`,
    not reachable by `git log` or code review. `tests/test_sssf_mode.py` even
    carried a `skipif(not PLUGIN.exists())` guard for exactly this: a fresh
    machine silently got no SSSF dsh preset at all. That is the "second copy to
    drift" CLAUDE.md's whole engine/template-mirror design exists to prevent —
    except here there was no second copy to drift *from*; the only copy lived
    outside version control.

    `sssf` itself must be a REAL directory, not a directory symlink to the repo
    source — confirmed against dsh's own code, not assumed: its preset scanner
    (`discovery.ts`) filters `readdir(..., {withFileTypes: true})` entries on
    `Dirent.isDirectory()`, which reflects the raw dirent type and does not
    follow symlinks, so a symlinked `sssf` directory is invisible to it
    entirely — verified live: it disappeared from the picker after exactly
    that swap, on a fresh restart, not merely a caching lag. Every FILE inside
    the real directory is linked instead (mirroring `install.py`'s own
    `LINK_FILES`, for the same reason: `agent.cordis.yml`'s `./tool-sssf.js`
    import must resolve beside a real `agent.cordis.yml`, and `import()`
    resolution, unlike a dirent scan, does follow a symlinked file).
    """
    if DSH_PRESET_LINK.is_symlink():
        # A stale directory-level symlink — this function's own first,
        # briefly-live version made exactly this mistake before the
        # discovery.ts finding above corrected it. `Path.is_symlink()` here
        # checks the link path itself, not what it resolves to, which is the
        # one call in this function that must not follow it: `mkdir(exist_ok
        # =True)` below would treat it as an already-satisfied directory and
        # never reach this branch, and the loop after it would then iterdir()
        # *through* the symlink and "back up" the repo's own source files as
        # if they were someone else's hand-authored intruders.
        DSH_PRESET_LINK.unlink()
    DSH_PRESET_LINK.mkdir(parents=True, exist_ok=True)
    sources = {p.name: p for p in DSH_PRESET_SOURCE.iterdir() if p.is_file()}
    changed = False
    # Pass 1: clear out anything that is not already a correct link — so pass
    # 2 can create every missing link without first checking what is in its
    # way. A symlink whose name matches but whose target is stale or broken
    # must be removed here, not skipped: left in place, the second pass's
    # symlink_to() would raise on the path it already occupies.
    for existing in list(DSH_PRESET_LINK.iterdir()):
        correct = (existing.is_symlink() and existing.name in sources
                  and existing.resolve() == sources[existing.name].resolve())
        if correct:
            continue
        if existing.is_symlink():
            # A symlink is never authored content, whatever it resolves to —
            # safe to remove outright, unlike the real-file/directory case
            # below. Checking this before is_file() matters: is_file() is also
            # true for a symlink that resolves to a file, which would
            # otherwise take this branch for the wrong reason and skip the
            # backup a REAL file below gets.
            existing.unlink()
        else:
            # A real, hand-authored file or directory predates this fix on
            # this machine. Back it up rather than deleting authored content
            # nobody asked to lose — a preset carries the trust of shell
            # access, so overwriting one silently is not this script's call.
            backup = existing.with_name(f"{existing.name}.pre-link-backup")
            if backup.exists():
                shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
            existing.rename(backup)
            print(f"  moved the old hand-authored {existing.name} to {backup}")
        changed = True
    # Pass 2: every survivor from pass 1 is already correct, so this only
    # creates what pass 1 just removed or what never existed.
    for name, source in sources.items():
        target = DSH_PRESET_LINK / name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(source)
            changed = True
    return changed


def install_units() -> set[str]:
    """Render both unit files from the repo templates. Returns the units changed.

    Rendering on every `up` is what keeps this working after a bun or node
    upgrade, and makes the templates in the repo the only definition. The
    caller needs to know which files changed: a rewritten unit that is not
    restarted leaves a process running under the previous definition, and for
    the dsh UI that definition includes the working directory — which is the
    repo its agent edits.
    """
    bun = require("bun", Path.home() / ".bun/bin/bun")
    node = require("node")
    dsh = install_dsh_shim(node)
    root = sslf_root()
    require_sslf_build(root)
    substitutions = {
        "@@VISUALIZER@@": str(VISUALIZER),
        # Nothing here may depend on the invocation directory: a unit that
        # differs per factory is rewritten and restarted on every `just go`
        # from a different repo, for no gain.
        "@@HOME@@": str(Path.home()),
        "@@PORT@@": str(visualizer_port()),
        "@@DSH_PORT@@": str(dsh_port()),
        "@@AUTHORITIES@@": str(AUTHORITIES),
        "@@BUN@@": str(bun),
        "@@DSH@@": str(dsh),
        "@@PATH@@": unit_path_env(bun, node, dsh),
        "@@NODE@@": str(node),
        "@@SSLF_ROOT@@": str(root),
        "@@SSLF_API_PORT@@": str(sslf_api_port()),
        "@@SSLF_WEB_PORT@@": str(sslf_web_port()),
        "@@OMNIROUTE_BIN@@": str(find_omniroute()),
        "@@OMNIROUTE_PORT@@": str(omniroute_port()),
    }
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    changed: set[str] = set()
    for template in sorted(UNIT_TEMPLATES.glob("*.service")):
        rendered = template.read_text()
        for token, value in substitutions.items():
            rendered = rendered.replace(token, value)
        target = UNIT_DIR / template.name
        if not target.exists() or target.read_text() != rendered:
            target.write_text(rendered)
            changed.add(template.stem)
    systemctl("daemon-reload")
    return changed


def tailnet_authorities(port: int) -> list[str]:
    """Every `host:port` a tailnet browser can reach this port by; [] when down."""
    result = run(["bash", str(AUTHORITIES), str(port)])
    return [line for line in result.stdout.splitlines() if line.strip()]


def port_owner(port: int) -> int | None:
    """The pid listening on a loopback port, if any — `ss` is always present."""
    result = run(["ss", "-ltnpH"])
    for line in result.stdout.splitlines():
        local = line.split()[3] if len(line.split()) > 3 else ""
        if not local.endswith(f":{port}"):
            continue
        found = re.search(r"pid=(\d+)", line)
        if found:
            return int(found.group(1))
    return None


def command_line(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""


def free_port_for_unit(surface: Surface) -> str | None:
    """Stop a hand-started copy of *this* surface so the unit can bind.

    The dsh UI is easy to have left running from an npx cache, where it holds
    the port but carries no `--trusted-host` and so answers a phone with a bare
    403. Replacing it loses no history: dsh persists sessions to disk.

    The port is only claimed from a process whose command line is recognisably
    the same app. Anything else keeps it and the unit is left to fail loudly —
    these are ordinary port numbers, and killing a stranger's server because it
    got there first would be far worse than a start that reports EADDRINUSE.
    """
    if is_active(surface.unit):
        return None
    pid = port_owner(surface.port)
    if pid is None or pid == os.getpid():
        return None
    command = command_line(pid)
    if not any(mark in command for mark in surface.owns):
        return (f":{surface.port} is held by an unrelated process (pid {pid}) — "
                f"stop it, or set a different port, before {surface.label} can start")
    print(f"  replacing an unmanaged {surface.label} on :{surface.port} (pid {pid})")
    run(["kill", str(pid)])
    for _ in range(40):
        if port_owner(surface.port) is None:
            return None
        time.sleep(0.25)
    return f"pid {pid} still holds :{surface.port}"


def main_pid(unit: str) -> int | None:
    value = systemctl("show", "-p", "MainPID", "--value", unit).stdout.strip()
    return int(value) if value.isdigit() and value != "0" else None


def stale_allowlist(surface: Surface, expected: list[str]) -> bool:
    """True when the running process does not carry every expected authority.

    Every fence receives the list once, at launch — the visualizer through
    SSSF_TRUSTED_HOSTS, SSLF web through SSLF_TRUSTED_HOSTS, dsh through
    repeated `--trusted-host`. So bringing
    Tailscale up after the services started leaves them correct but unreachable,
    which looks exactly like a network fault. Reading the live process is what
    lets `up` notice and restart, instead of the user having to know.
    """
    if not expected or not surface.host_fence:
        return False
    pid = main_pid(surface.unit)
    if pid is None:
        return False
    carried = ""
    for name in ("cmdline", "environ"):
        try:
            carried += Path(f"/proc/{pid}/{name}").read_bytes().decode("utf-8", "replace")
        except OSError:
            return False
    return any(authority not in carried for authority in expected)


def ensure_serve(port: int) -> str | None:
    """Publish a loopback port on the tailnet. Returns an error to report, or None.

    `serve --bg` is persistent tailnet configuration rather than a child process:
    it outlives this command, survives a reboot, and re-running it is idempotent.
    """
    if not shutil.which("tailscale"):
        return "tailscale is not installed"
    # A raw TCP forward (the ecosystem justfile's `--tcp` style) already carries
    # HTTP, and tailscale refuses to layer `--http` on a port serving TCP.
    if tcp_forward(port) == f"localhost:{port}":
        return None
    result = run(["tailscale", "serve", "--bg", f"--http={port}", str(port)])
    if result.returncode == 0:
        return None
    lines = (result.stderr or result.stdout).strip().splitlines()
    message = [line for line in lines if line.startswith("error:")] or lines
    return message[-1] if message else f"tailscale serve failed for :{port}"


def tcp_forward(port: int) -> str | None:
    """The target a raw TCP serve forwards this port to, if any."""
    result = run(["tailscale", "serve", "status", "--json"])
    if result.returncode != 0:
        return None
    try:
        tcp = json.loads(result.stdout or "{}").get("TCP") or {}
    except json.JSONDecodeError:
        return None
    return (tcp.get(str(port)) or {}).get("TCPForward")


def tailscale_ready() -> bool:
    if not shutil.which("tailscale"):
        return False
    result = run(["tailscale", "status", "--json"])
    if result.returncode != 0:
        return False
    try:
        return json.loads(result.stdout).get("BackendState") == "Running"
    except json.JSONDecodeError:
        return False


def report(surface: Surface) -> None:
    """Print where a surface can be reached, local address last resort."""
    authorities = tailnet_authorities(surface.port) if surface.tailnet else []
    where = f"http://{authorities[0]}" if authorities else f"http://localhost:{surface.port}"
    print(f"  {surface.label:<18} {where}")


def up(_: argparse.Namespace) -> int:
    """Start whatever is down, publish both on the tailnet, say where they are.

    Starting rather than restarting is deliberate: `reload` already applied the
    fresh build to a running app, and restarting the dsh UI here would cut off
    whatever conversation is open in a browser for no reason at all.
    """
    rewritten = install_units()
    if install_dsh_preset():
        print(f"  installed the sssf dsh preset at {DSH_PRESET_LINK}")
    ready = tailscale_ready()
    problems: list[str] = []
    for surface in surfaces():
        blocked = free_port_for_unit(surface)
        if blocked:
            problems.append(blocked)
            continue
        authorities = tailnet_authorities(surface.port) if surface.tailnet else []
        reason = None
        if surface.unit in rewritten:
            reason = "its unit changed"
        elif stale_allowlist(surface, authorities):
            reason = "it started before the tailnet name existed"
        if reason and is_active(surface.unit):
            print(f"  restarting {surface.label}: {reason}")
        result = systemctl("restart" if reason else "start", surface.unit)
        if result.returncode != 0:
            problems.append(f"{surface.unit}: {(result.stderr or result.stdout).strip()}")
            continue
        systemctl("enable", "--quiet", surface.unit)
        if ready and surface.tailnet:
            failure = ensure_serve(surface.port)
            if failure:
                problems.append(f"tailnet :{surface.port}: {failure}")
    if not ready:
        print("Tailscale is not up — serving on localhost only.")
        print("  once, with a password:  sudo tailscale set --operator=$USER")
        print("  then:                   tailscale up --accept-routes")
    for surface in surfaces():
        report(surface)
    for problem in problems:
        print(f"  ! {problem}", file=sys.stderr)
    print("  logs: just logs   stop: just kill")
    return 1 if problems else 0


def down(_: argparse.Namespace) -> int:
    """Stop every surface. The tailnet config is left alone: it publishes
    nothing while the ports are closed, and keeps the URLs stable across a
    restart."""
    for surface in surfaces():
        systemctl("stop", surface.unit)
        print(f"stopped {surface.label}")
    return 0


def reload(_: argparse.Namespace) -> int:
    """Apply a fresh build to every running surface that serves one.

    The visualizer reads its client from dist/ per request, but its Bun server is
    the process under test whenever server/*.ts changed. SSLF needs a restart
    for both halves: the API runs dist/ once loaded, and `vite preview` indexes
    dist/ at startup, so new hashed asset names would 404 until it restarts.
    The dsh UI and OmniRoute are not built here; restarting them would cut off an
    open session or in-flight model calls.
    """
    for surface in surfaces():
        if surface.unit not in REBUILT_UNITS:
            continue
        if is_active(surface.unit):
            systemctl("restart", surface.unit)
            print(f"{surface.label} restarted on the new build")
        else:
            print(f"{surface.label} is not running — `just go` will start it on this build")
    return 0


def status(_: argparse.Namespace) -> int:
    """Print each surface's state and the one URL that actually reaches it.

    `tailnet_authorities()` returns several forms (FQDN, short name, each IP)
    because that is the right list for the *fence* — SSSF_TRUSTED_HOSTS and
    --trusted-host both widen correctly on any of them. `tailscale serve`'s own
    routing is stricter: its config is keyed by the FQDN alone (confirmed via
    `tailscale serve status --json`, whose "Web" map only ever has
    "<fqdn>:<port>" as a key) — a request addressed to the short name or the
    bare IP is 404'd by tailscaled itself before it ever reaches this app, our
    fence's own permissiveness notwithstanding. Printing every authority here
    once advertised two URLs that looked reachable and were not; report() (the
    one `up` already uses) never had this bug, because it only ever printed
    authorities[0] — which tailnet_authorities() always orders FQDN-first.
    """
    for surface in surfaces():
        state = "running" if is_active(surface.unit) else "stopped"
        print(f"{surface.label:<18} {state:<8} :{surface.port}")
        if not surface.tailnet:
            print(f"  local    http://localhost:{surface.port}")
            continue
        authorities = tailnet_authorities(surface.port)
        if authorities:
            print(f"  tailnet  http://{authorities[0]}")
    if not tailscale_ready():
        print("Tailscale is not up — localhost only")
    return 0


def dsh_url(_: argparse.Namespace) -> int:
    """Print the current, ready-to-click dsh web URL, token included.

    dsh mints a fresh launch token every boot and accepts it only as a
    `?token=` query param on `GET /` — by design: "there is no method-specific
    loopback tier" (the connection package's own words), so even localhost
    gets this check, because the surface behind it is full shell and
    filesystem access. The token itself cannot be fixed to a known value
    without defeating that: a predictable bootstrap secret would let anyone
    who ever saw it authenticate forever. What is fixable is *finding* it —
    this used to mean grepping journalctl by hand, which is exactly the
    "wastes time" complaint that prompted this command.

    Once a browser exchanges the token for a signed cookie (30 days by
    default), it does not need the token again unless the process restarts or
    the cookie's authority (the exact host:port it was issued for) changes —
    so pasting the SAME url this prints every time avoids most re-logins.
    """
    if not is_active(DSH_UNIT):
        print("dsh web is not running — `just go` will start it", file=sys.stderr)
        return 1
    log = run(["journalctl", "--user", "-u", DSH_UNIT, "-n", "200",
              "--no-pager", "--output=cat"])
    # journalctl prints oldest-first, and a unit that has restarted several
    # times carries one startup line per boot — the *last* match is the
    # current process's. re.search alone found the first, so a machine with
    # any restart history handed back a dead token for an old process; caught
    # live, not assumed, by comparing this command's own output against the
    # unit's actual start time.
    matches = re.findall(r"dsh web: http://[^\s]+\?token=([\w-]+)", log.stdout)
    if not matches:
        print("no startup line found in this unit's recent log — it may "
              "have restarted long enough ago to scroll past 200 lines; "
              "`just logs` and search for one yourself", file=sys.stderr)
        return 1
    token = matches[-1]
    authorities = tailnet_authorities(dsh_port())
    host = authorities[0] if authorities else f"localhost:{dsh_port()}"
    print(f"http://{host}/?token={token}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {"up": up, "down": down, "reload": reload, "status": status, "dsh-url": dsh_url}
    parser.add_argument("action", choices=sorted(actions))
    arguments = parser.parse_args(argv)
    return actions[arguments.action](arguments)


if __name__ == "__main__":
    raise SystemExit(main())
