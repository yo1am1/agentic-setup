"""End-to-end `make ai` tests on a temporary fixture holding only the environment files."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
# Only the agent environment and its root integration files; no application code.
FIXTURE_FILES = (".gitignore", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "Makefile", "README.md")
OPTIONAL = ("cavecrew", "council", "herdr", "humanizer", "specsmd")
CORE = ("caveman", "caveman-commit", "project-flow")
ROLES = sorted(p.stem for p in (SOURCE / ".agents/agents").glob("*.md") if p.name != "README.md")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def ignore_generated(directory, names):
    ignored = {name for name in names if name == "__pycache__"}
    if Path(directory) == SOURCE / ".agents/skills":
        ignored |= set(OPTIONAL) & set(names)
    return ignored | ({".optional-sync-manifest.json"} & set(names))


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mode)
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root, self.home = base / "repo", base / "home"
        self.home.mkdir()
        shutil.copytree(SOURCE / ".agents", self.root / ".agents", ignore=ignore_generated)
        for name in FIXTURE_FILES:
            shutil.copy2(SOURCE / name, self.root / name)
        self.git("init", "-q")
        self.env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        self.canonical = snapshot(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, text=True,
                              capture_output=True).stdout

    def run_cmd(self, *args, ok=True):
        result = subprocess.run(args, cwd=self.root, env=self.env, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def make_ai(self, mode, ok=True):
        return self.run_cmd("make", "--no-print-directory", "ai", mode, ok=ok)

    def check_hosts(self, mode):
        for host in ("claude", "codex", "gemini"):
            self.run_cmd("python3", ".agents/adapters/sync.py", "--host", host, "--layout", mode, "--check")

    def assert_canonical_unchanged(self):
        current = snapshot(self.root)
        for rel, value in self.canonical.items():
            self.assertEqual(current.get(rel), value, rel)

    def assert_simple(self):
        for skill in CORE:
            self.assertTrue((self.root / f".claude/skills/{skill}/SKILL.md").is_file())
        for name in OPTIONAL:
            self.assertFalse((self.root / f".agents/skills/{name}").exists(), name)
            self.assertFalse((self.root / f".claude/skills/{name}").exists(), name)
        for host, suffix in (("claude", "md"), ("codex", "toml"), ("gemini", "md")):
            for role in ROLES:
                self.assertFalse((self.root / f".{host}/agents/{role}.{suffix}").exists(), role)
            self.assertFalse((self.root / f".{host}/workflows").exists(), host)
            self.assertIn("Simple layout", (self.root / f".{host}/STARTUP.md").read_text())
        self.check_hosts("simple")

    def assert_full(self):
        self.assertEqual(len(ROLES), 7)
        for host, suffix in (("claude", "md"), ("codex", "toml"), ("gemini", "md")):
            for role in ROLES:
                self.assertTrue((self.root / f".{host}/agents/{role}.{suffix}").is_file(), role)
        for name in OPTIONAL:
            # Codex/Gemini discover .agents/skills; Claude discovers .claude/skills.
            self.assertTrue((self.root / f".agents/skills/{name}/SKILL.md").is_file(), name)
            self.assertTrue((self.root / f".claude/skills/{name}/SKILL.md").is_file(), name)
        humanizer = (self.root / ".claude/skills/humanizer/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", humanizer)
        startup = (self.root / ".claude/STARTUP.md").read_text()
        self.assertIn("Humanizer is prose-only", startup)
        self.assertIn("solo work remain default", startup)
        self.check_hosts("full")

    def assert_links_resolve(self, before):
        generated = set(snapshot(self.root)) - set(before)
        for rel in sorted(path for path in generated if path.endswith("SKILL.md") or "/agents/" in path
                          or "/wrappers/" in path):
            text = (self.root / rel).read_text()
            for link in LINK.findall(text):
                target = link.split("#", 1)[0].split("?", 1)[0]
                if not target or re.match(r"[a-z]+:", target):
                    continue
                base = self.root if target.startswith(".agents/") else (self.root / rel).parent
                self.assertTrue((base / target).exists(), f"{rel}: {link}")

    def test_bare_make_ai_shows_choices_and_installs_nothing(self):
        result = self.run_cmd("make", "--no-print-directory", "ai")
        self.assertIn("make ai simple", result.stdout)
        self.assertIn("make ai full", result.stdout)
        self.assertEqual(snapshot(self.root), self.canonical)
        self.assertEqual(self.make_ai("full simple", ok=False).returncode, 2)
        self.assertEqual(snapshot(self.root), self.canonical)

    def test_standalone_modes_fail_with_usage_and_install_nothing(self):
        for mode in ("simple", "full"):
            with self.subTest(mode=mode):
                result = self.run_cmd("make", mode, ok=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage: make ai simple OR make ai full", result.stderr)
                self.assertEqual(snapshot(self.root), self.canonical)

    def test_mode_transitions_are_idempotent_and_preserve_user_files(self):
        user_files = {
            ".claude/settings.json": b'{"user": true}\n',
            ".claude/agents/mine.md": b"user role\n",
            ".codex/config.toml": b"model = 'user'\n",
            ".gemini/settings.json": b'{"user": true}\n',
            ".agents/skills/mine/SKILL.md": b"---\nname: mine\ndescription: user\n---\n",
        }
        for rel, content in user_files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(content)
        before = snapshot(self.root)
        hooks = sorted(p.name for p in (self.root / ".git/hooks").iterdir())
        for mode in ("simple", "full", "simple", "full", "simple"):
            with self.subTest(mode=mode):
                self.make_ai(mode)
                installed = snapshot(self.root)
                self.make_ai(mode)
                self.assertEqual(snapshot(self.root), installed, "second run must not change files")
                getattr(self, f"assert_{mode}")()
                if mode == "full":
                    self.assert_links_resolve(before)
                self.assert_canonical_unchanged()
                for rel, content in user_files.items():
                    self.assertEqual((self.root / rel).read_bytes(), content, rel)
                # Generated output stays ignored; canonical and user files stay visible.
                untracked = set(self.git("ls-files", "--others", "--exclude-standard").split())
                self.assertEqual(untracked, set(self.canonical) | set(user_files))
                self.assertEqual(sorted(p.name for p in (self.root / ".git/hooks").iterdir()), hooks)
                hooks_path = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                                            cwd=self.root, capture_output=True)
                self.assertEqual(hooks_path.returncode, 1, "installation must not set core.hooksPath")
                self.assertEqual(list(self.home.iterdir()), [], "nothing written outside the repository")
                for app_file in ("pyproject.toml", "uv.lock", ".venv", "node_modules"):
                    self.assertFalse((self.root / app_file).exists(), app_file)

    def test_shared_optional_copies_follow_remaining_full_hosts(self):
        sync = ("python3", ".agents/adapters/sync.py", "--write")
        self.run_cmd(*sync, "--host", "codex", "--layout", "full")
        self.run_cmd(*sync, "--host", "gemini", "--layout", "full")
        self.run_cmd(*sync, "--host", "codex", "--layout", "simple")
        self.assertTrue((self.root / ".agents/skills/council/SKILL.md").is_file())
        self.assertFalse((self.root / ".codex/agents").exists())
        self.assertTrue((self.root / ".gemini/agents").is_dir())
        self.make_ai("simple")
        self.assert_simple()
        self.assert_canonical_unchanged()

    def test_unmanaged_collision_fails_before_any_write(self):
        collision = self.root / ".agents/skills/council/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("user council\n")
        before = snapshot(self.root)
        result = self.make_ai("full", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite existing unmanaged files", result.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_symlinked_host_directory_is_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / ".claude").symlink_to(outside, target_is_directory=True)
        result = self.make_ai("simple", ok=False)
        self.assertIn("refusing symlink", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
