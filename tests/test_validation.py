import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ValidationCheck(unittest.TestCase):
    def test_invalid_metadata_and_source_drift_are_rejected(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(source / ".agents", root / ".agents")
            shutil.copytree(source / "scripts", root / "scripts")
            shutil.copy2(source / "source-manifest.json", root / "source-manifest.json")
            shutil.copytree(source / "licenses", root / "licenses")
            skill = root / ".agents/skills/council/SKILL.md"
            original = skill.read_text()
            for text in (
                original.replace("name: council", "name: wrong"),
                original + "\nUnrecorded instruction change\n",
            ):
                skill.write_text(text)
                result = subprocess.run(
                    [sys.executable, str(root / "scripts/validate.py")],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
            skill.write_text(original)
            result = subprocess.run(
                [sys.executable, str(root / "scripts/validate.py")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_adapter_copies_helpers_and_detects_entrypoint_drift(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(source / ".agents", root / ".agents")
            shutil.copytree(source / "scripts", root / "scripts")
            command = [sys.executable, str(root / "scripts/sync_agent_adapters.py")]
            written = subprocess.run(command + ["--write"], capture_output=True, text=True)
            self.assertEqual(written.returncode, 0, written.stderr)
            for source_path in (root / ".agents/skills").rglob("*"):
                if source_path.is_file() and source_path.name != "SKILL.md":
                    generated = root / ".claude/skills" / source_path.relative_to(root / ".agents/skills")
                    self.assertEqual(generated.read_bytes(), source_path.read_bytes())
            checked = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            helper = root / ".claude/skills/autoresearch/templates/train.py"
            helper.write_text("# drift\n")
            checked = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertNotEqual(checked.returncode, 0)


if __name__ == "__main__":
    unittest.main()
