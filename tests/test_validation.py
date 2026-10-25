import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidationCheck(unittest.TestCase):
    def test_generated_optional_discovery_copies_are_not_tracked(self):
        optional_names = [
            path.parent.name
            for path in (ROOT / '.agents/optional').glob('*/SKILL.md')
        ]
        result = subprocess.run(
            ['git', 'ls-files', '--', *[
                f'.agents/skills/{name}/' for name in optional_names
            ]], cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout, '')

    def test_invalid_metadata_and_source_drift_are_rejected(self):
        manifest = json.loads((ROOT / 'source-manifest.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for entry in manifest:
                relative = entry['path']
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            shutil.copy2(ROOT / 'source-manifest.json', target / 'source-manifest.json')
            command = [sys.executable, str(target / 'scripts/validate.py')]
            for relative, name in (
                ('.agents/skills/project-flow/SKILL.md', 'project-flow'),
                ('library/.agents/skills/council/SKILL.md', 'council'),
            ):
                skill = target / relative
                original = skill.read_text()
                for changed in (
                    original.replace(f'name: {name}', 'name: wrong'),
                    original + '\nUnrecorded instruction change\n',
                ):
                    skill.write_text(changed)
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                skill.write_text(original)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_compatibility_entrypoint_uses_current_installer_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            shutil.copytree(ROOT / '.agents', target / '.agents',
                            ignore=shutil.ignore_patterns('__pycache__'))
            (target / 'scripts').mkdir()
            shutil.copy2(ROOT / 'scripts/sync_agent_adapters.py', target / 'scripts/sync_agent_adapters.py')
            command = [sys.executable, str(target / 'scripts/sync_agent_adapters.py')]
            result = subprocess.run(command, capture_output=True, text=True, cwd=target)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Dry-run: layout=simple', result.stdout)
            for host in ('claude', 'codex', 'gemini'):
                self.assertFalse((target / f'.{host}').exists())


if __name__ == '__main__':
    unittest.main()
