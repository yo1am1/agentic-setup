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


if __name__ == "__main__":
    unittest.main()
