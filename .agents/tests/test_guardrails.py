import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


MODULE = Path(__file__).parents[1] / "guardrails/checks.py"
spec = importlib.util.spec_from_file_location("guardrail_checks", MODULE)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class GitRepo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root, self.old_policy = checks.ROOT, checks.POLICY
        checks.ROOT = self.root
        checks.POLICY = {"python_paths": ["*.py"], "project_checks": [],
                         "guardrail_tests": ["python3", "-c", "raise SystemExit(0)"]}
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        policy = self.root / ".agents/guardrails/policy.json"
        policy.parent.mkdir(parents=True)
        policy.write_text('{"python_paths": ["*.py"], "project_checks": [["python3", "-c", "pass"]], "guardrail_tests": ["python3", "-c", "pass"]}')
        self.git("add", ".")
        self.git("commit", "-qm", "policy")

    def tearDown(self):
        checks.ROOT, checks.POLICY = self.old_root, self.old_policy
        self.temp.cleanup()

    def git(self, *args, **kwargs):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              text=True, capture_output=True, **kwargs).stdout.strip()

    def commit(self, name, content):
        (self.root / name).write_text(content)
        self.git("add", name)
        self.git("commit", "-qm", "change")
        return self.git("rev-parse", "HEAD")

    def test_member_config_requires_project_checks(self):
        self.assertTrue(checks.requires_python(["agent-runtime/pyproject.toml"]))
        self.assertTrue(checks.requires_python(["mcp-sandbox/pyproject.toml"]))
        self.assertFalse(checks.requires_python(["docs/README.md"]))

    def test_snapshot_checks_use_snapshot_environment(self):
        tree = self.git("write-tree")
        with patch.dict(os.environ, {"UV_PROJECT_ENVIRONMENT": "/wrong/venv", "VIRTUAL_ENV": "/wrong/venv"}):
            with patch.object(checks.subprocess, "run", wraps=subprocess.run) as runner:
                self.assertTrue(checks.run_checks(tree, ["agent-runtime/pyproject.toml"]))
        command = next(call for call in runner.call_args_list if call.args[0][0] == "python3")
        self.assertEqual(command.kwargs["env"]["UV_PROJECT_ENVIRONMENT"], str(command.kwargs["cwd"] / ".venv"))
        self.assertNotIn("VIRTUAL_ENV", command.kwargs["env"])

    def test_module_loads_outside_git_for_snapshot_self_checks(self):
        with tempfile.TemporaryDirectory(prefix="guardrail-import-") as outside:
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import runpy; runpy.run_path({str(MODULE.resolve())!r}, run_name='probe')"],
                cwd=outside, text=True, capture_output=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_snapshot_is_index_tree_with_partial_staging_and_deletion(self):
        self.commit("kept.py", "old\n")
        (self.root / "kept.py").write_text("staged\n")
        self.git("add", "kept.py")
        (self.root / "kept.py").write_text("unstaged\n")
        tree = self.git("write-tree")
        with tempfile.TemporaryDirectory() as dest:
            checks.snapshot(tree, dest)
            self.assertEqual((Path(dest) / "kept.py").read_text(), "staged\n")
        (self.root / "kept.py").unlink()
        self.git("add", "-u")
        tree = self.git("write-tree")
        with tempfile.TemporaryDirectory() as dest:
            checks.snapshot(tree, dest)
            self.assertFalse((Path(dest) / "kept.py").exists())

    def test_precommit_fails_when_check_fails_and_does_not_mutate_index(self):
        self.commit("base.txt", "base\n")
        (self.root / "bad.py").write_text("bad\n")
        policy = self.root / ".agents/guardrails/policy.json"
        policy.write_text('{"python_paths": ["*.py"], "project_checks": [["python3", "-c", "raise SystemExit(3)"]], "guardrail_tests": ["python3", "-c", "pass"]}')
        self.git("add", "bad.py")
        self.git("add", str(policy.relative_to(self.root)))
        original = self.git("write-tree")
        old_env = os.environ.get("GUARDRAILS_AUTHORIZED")
        os.environ["GUARDRAILS_AUTHORIZED"] = "1"
        try:
            self.assertEqual(checks.pre_commit(), 1)
            self.assertEqual(self.git("write-tree"), original)
        finally:
            if old_env is None:
                os.environ.pop("GUARDRAILS_AUTHORIZED", None)
            else:
                os.environ["GUARDRAILS_AUTHORIZED"] = old_env

    def test_pre_push_checks_each_ref_and_full_tree_without_remote_base(self):
        first = self.commit("a.py", "a\n")
        self.git("branch", "a", first)
        second = self.commit("b.py", "b\n")
        self.git("branch", "b", second)
        payload = f"refs/heads/a {first} refs/heads/a {'0' * 40}\nrefs/heads/b {second} refs/heads/b {first}\n"
        old_env = os.environ.get("GUARDRAILS_AUTHORIZED")
        os.environ["GUARDRAILS_AUTHORIZED"] = "1"
        try:
            self.assertEqual(checks.pre_push(payload), 0)
            self.assertEqual(checks.pre_push("malformed\n"), 1)
        finally:
            if old_env is None:
                os.environ.pop("GUARDRAILS_AUTHORIZED", None)
            else:
                os.environ["GUARDRAILS_AUTHORIZED"] = old_env


if __name__ == "__main__":
    unittest.main()
