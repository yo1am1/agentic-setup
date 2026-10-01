import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ValidationCheck(unittest.TestCase):
    def test_invalid_metadata_and_broken_link_are_rejected(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(source / ".agents", root / ".agents")
            shutil.copytree(source / "scripts", root / "scripts")
            skill = root / ".agents/skills/fusion/SKILL.md"
            original = skill.read_text()
            for text in (
                original.replace("name: fusion", "name: wrong"),
                original + "\n[missing](missing.md)\n",
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
