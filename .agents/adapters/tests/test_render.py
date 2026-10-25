import json
import tempfile
import tomllib
import unittest
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import render
import sync


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.role = render.Role("Code Reviewer", "Review changes", "Read [contract](README.md). Preserve evidence.")

    def test_renders_supported_host_paths_and_preserves_role_body(self):
        expected = {
            "claude": ".claude/agents/code-reviewer.md",
            "codex": ".codex/agents/code-reviewer.toml",
            "gemini": ".gemini/agents/code-reviewer.md",
            "copilot": ".github/agents/code-reviewer.agent.md",
            "cursor": ".cursor/skills/code-reviewer/SKILL.md",
            "pi": ".pi/skills/code-reviewer/SKILL.md",
        }
        for host, path in expected.items():
            with self.subTest(host=host):
                files = render.render(host, [self.role])
                self.assertIn(path, files)
                self.assertIn("Preserve evidence.", files[path])
                self.assertIn("Humanizer is prose-only", files[path])
                target = re.search(r"\]\(([^)]+)\)", files[path]).group(1)
                canonical = ".agents/agents/README.md"
                self.assertEqual(target, canonical)
        codex_files = render.render("codex", [self.role])
        self.assertEqual(codex_files["AGENTS.md"], render.STARTUP)

    def test_role_links_rebase_to_existing_canonical_sources(self):
        root = Path(__file__).parents[3]
        roles = render.load_roles(root)
        link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
        for host in ("claude", "codex", "gemini"):
            files = render.render(host, roles)
            for name, content in files.items():
                if "/agents/" not in name:
                    continue
                with self.subTest(host=host, file=name):
                    body = (
                        tomllib.loads(content)["developer_instructions"]
                        if name.endswith(".toml")
                        else content
                    )
                    links = link_pattern.findall(body)
                    self.assertTrue(links)
                    for target in links:
                        self.assertTrue(target.startswith(".agents/"), target)
                        self.assertTrue((root / target.split("#", 1)[0]).is_file(), target)
        coordinator = render.role_body("claude", next(r for r in roles if r.name == "coordinator"))
        self.assertIn(".agents/skills/project-flow/SKILL.md", coordinator)
        self.assertIn(".agents/workflows/team.md", coordinator)
        engineer = render.role_body("claude", next(r for r in roles if r.name == "engineer"))
        self.assertIn(".agents/agents/README.md", engineer)

    def test_role_link_rebase_preserves_external_urls_and_fragments(self):
        role = render.Role(
            "Reviewer",
            "Review changes",
            "[source](../rules/README.md#details) [web](https://example.com/a#b) [anchor](#here)",
        )
        body = render.role_body("claude", role)
        self.assertIn("[source](.agents/rules/README.md#details)", body)
        self.assertIn("[web](https://example.com/a#b)", body)
        self.assertIn("[anchor](#here)", body)

    def test_role_frontmatter_requires_name_and_description(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.md"
            path.write_text("---\nname: Reviewer\n---\nbody", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "name and description"):
                render.parse_role(path)

    def test_unverified_hosts_have_no_renderer(self):
        for host in ("dsh", "kimi"):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "no verified renderer"):
                render.render(host, [self.role])

    def test_write_refuses_existing_file_before_writing_any_sibling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generated = root / ".claude/agents/code-reviewer.md"
            generated.parent.mkdir(parents=True)
            generated.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                render.write_files(root, {
                    ".claude/agents/code-reviewer.md": "replace",
                    ".claude/agents/engineer.md": "new",
                })
            self.assertEqual(generated.read_text(encoding="utf-8"), "keep")
            self.assertFalse((root / ".claude/agents/engineer.md").exists())

    def test_documented_host_matrix_matches_renderers_and_fail_closed_hosts(self):
        readme = Path(__file__).parents[1].joinpath("README.md").read_text(encoding="utf-8")
        for host in (*render.HOSTS, "dsh", "kimi"):
            with self.subTest(host=host):
                self.assertIn(host, readme.lower())
        self.assertIn("herdr / orca", readme.lower())
        self.assertIn("Council stays Herdr-only", readme)
        self.assertIn("never changes native host directories", readme)

    @unittest.skipUnless(
        (Path(__file__).parents[3] / ".agents/guardrails/README.md").is_file(),
        "guardrails module is integrated in the main checkout",
    )
    def test_guardrails_cross_module_link_resolves(self):
        root = Path(__file__).parents[3]
        readme = root / ".agents/adapters/README.md"
        target = (readme.parent / "../guardrails/README.md").resolve()
        self.assertTrue(target.is_relative_to(root.resolve()))
        self.assertTrue(target.is_file())

    def test_simple_vs_full_layout_role_and_skill_filtering(self):
        root = Path(__file__).parents[3]
        full_roles = {render.slug(r.name) for r in render.load_roles(root, "full")}
        simple_roles = {render.slug(r.name) for r in render.load_roles(root, "simple")}
        self.assertEqual(
            simple_roles,
            set(),
        )
        self.assertTrue(simple_roles.issubset(full_roles))
        self.assertIn("engineer", full_roles)
        self.assertNotIn("engineer", simple_roles)

        simple_skills = {p.name for p in sync.iter_skill_dirs(root, "simple")}
        self.assertEqual(simple_skills, {"caveman", "caveman-commit", "project-flow"})

    def test_commit_skill_is_available_in_both_layouts(self):
        root = Path(__file__).parents[3]
        relative = "skills/caveman-commit/SKILL.md"
        canonical = root / ".agents" / relative
        for layout in ("simple", "full"):
            for host in sync.PRIMARY_HOSTS:
                with self.subTest(layout=layout, host=host):
                    plan = sync.build_plan([host], root, layout)
                    if host == "claude":
                        self.assertEqual(plan.files[f".claude/{relative}"], canonical.read_bytes())
                    self.assertIn(
                        f".agents/{relative}",
                        plan.files[f".{host}/STARTUP.md"].decode(),
                    )

    def test_sync_switches_layouts_and_cleans_stale_managed_files(self):
        root = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            full_plan = sync.build_plan(["codex", "claude"], root, layout="full")
            written, removed = sync.apply_plan(target, full_plan, ["codex", "claude"], "full")
            self.assertEqual(removed, [])
            self.assertTrue((target / ".codex/agents/engineer.toml").is_file())
            self.assertTrue((target / ".claude/agents/engineer.md").is_file())
            self.assertFalse(any(path.startswith(".codex/skills/") for path in full_plan.files))

            self.assertTrue((target / ".agents/skills/council/SKILL.md").is_file())

            # Simple keeps only core skills and startup guidance: no roles, workflows or optional copies.
            simple_plan = sync.build_plan(["codex", "claude"], root, layout="simple")
            _, removed_on_switch = sync.apply_plan(target, simple_plan, ["codex", "claude"], "simple")
            self.assertIn(".codex/agents/engineer.toml", removed_on_switch)
            self.assertIn(".agents/skills/council/SKILL.md", removed_on_switch)
            for role in ("engineer", "coordinator", "simplifier", "devils-advocate", "code-reviewer"):
                self.assertFalse((target / f".codex/agents/{role}.toml").exists(), role)
                self.assertFalse((target / f".claude/agents/{role}.md").exists(), role)
            self.assertFalse((target / ".codex/workflows").exists())
            self.assertFalse((target / ".agents/skills/council").exists())
            self.assertTrue((target / ".claude/skills/caveman/SKILL.md").is_file())
            self.assertFalse(any(path.startswith(".codex/skills/") for path in simple_plan.files))
            self.assertEqual(sync.check_plan(target, simple_plan, ["codex", "claude"]), [])

    def test_syncing_hosts_separately_preserves_each_host_files(self):
        root = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            for host in ("claude", "codex", "gemini"):
                plan = sync.build_plan([host], root, layout="simple")
                sync.apply_plan(target, plan, [host], "simple")
            self.assertFalse((target / ".claude/agents/coordinator.md").exists())
            self.assertFalse((target / ".codex/agents/coordinator.toml").exists())
            self.assertFalse((target / ".gemini/agents/coordinator.md").exists())

    def test_all_to_single_host_layout_roundtrip_preserves_unselected_hosts(self):
        source = Path(__file__).parents[3]
        hosts = list(render.HOSTS)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            sync.apply_plan(target, sync.build_plan(hosts, source), hosts, "full")
            settings = target / ".claude/settings.json"
            settings.write_bytes(b'{"sentinel": true}')
            untouched = {
                p.relative_to(target): p.read_bytes()
                for host in ("copilot", "cursor", "pi")
                for p in (target / sync.host_prefix(host)).rglob("*") if p.is_file()
            }
            for layout in ("simple", "full"):
                for host in ("claude", "codex", "gemini"):
                    plan = sync.build_plan([host], source, layout)
                    # Check must also find stale ownership in the other manifest style.
                    self.assertTrue(sync.check_plan(target, plan, [host]))
                    sync.apply_plan(target, plan, [host], layout)
                    self.assertEqual(sync.check_plan(target, plan, [host]), [])
                    self.assertEqual(settings.read_bytes(), b'{"sentinel": true}')
                    for rel, content in untouched.items():
                        self.assertEqual((target / rel).read_bytes(), content)
            self.assertFalse(any(
                rel.startswith((".claude/", ".codex/", ".gemini/"))
                for rel in sync.read_manifest(target / sync.MANIFEST_NAME)
            ))

    def test_single_hosts_to_all_layout_roundtrip(self):
        source = Path(__file__).parents[3]
        hosts = list(render.HOSTS)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            for host in hosts:
                sync.apply_plan(target, sync.build_plan([host], source), [host], "full")
            settings = target / ".claude/settings.json"
            settings.write_bytes(b"keep settings")
            for layout in ("simple", "full"):
                plan = sync.build_plan(hosts, source, layout)
                self.assertTrue(sync.check_plan(target, plan, hosts))
                sync.apply_plan(target, plan, hosts, layout)
                self.assertEqual(sync.check_plan(target, plan, hosts), [])
                self.assertEqual(settings.read_bytes(), b"keep settings")
            for host in hosts:
                self.assertEqual(sync.read_manifest(sync.manifest_path(target, [host])), set())

    def test_transferred_ownership_cannot_claim_recreated_unmanaged_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            rel = ".claude/agents/engineer.md"
            full = sync.SyncPlan({rel: b"managed"}, set())
            sync.apply_plan(target, full, ["claude", "codex"], "full")
            sync.apply_plan(target, sync.SyncPlan({}, set()), ["claude"], "simple")
            user_file = target / rel
            user_file.parent.mkdir(parents=True, exist_ok=True)
            user_file.write_bytes(b"user recreated")
            with self.assertRaisesRegex(FileExistsError, "unmanaged"):
                sync.apply_plan(target, full, ["claude", "codex"], "full")
            self.assertEqual(user_file.read_bytes(), b"user recreated")

    def test_host_manifest_cannot_claim_another_hosts_files(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            other = target / ".codex/keep.toml"
            other.parent.mkdir()
            other.write_bytes(b"keep")
            manifest = sync.manifest_path(target, ["claude"])
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"managed_files": [".codex/keep.toml"]}))
            sync.apply_plan(target, sync.SyncPlan({}, set()), ["claude", "codex"], "simple")
            self.assertEqual(other.read_bytes(), b"keep")

    def test_shared_ownership_refuses_symlink_manifests(self):
        for relative, hosts in (
            (sync.MANIFEST_NAME, ["claude"]),
            (f".claude/{sync.MANIFEST_NAME}", ["claude", "codex"]),
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
                target = Path(temp)
                external = Path(outside) / "manifest.json"
                external.write_text('{"managed_files": []}')
                manifest = target / relative
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.symlink_to(external)
                plan = sync.SyncPlan({".claude/new.md": b"new"}, set())
                with self.assertRaisesRegex(ValueError, "refusing symlink"):
                    sync.apply_plan(target, plan, hosts, "full")
                self.assertFalse((target / ".claude/new.md").exists())
                self.assertEqual(external.read_text(), '{"managed_files": []}')

    def test_shared_manifest_rejects_escape_and_symlink_before_mutation(self):
        for entry in ("../keep", ".claude/linked/keep"):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
                target = Path(temp)
                (target / ".claude").mkdir()
                (target / ".claude/linked").symlink_to(outside, target_is_directory=True)
                manifest = target / sync.MANIFEST_NAME
                manifest.write_text(json.dumps({"managed_files": [entry]}))
                before = manifest.read_bytes()
                plan = sync.SyncPlan({".claude/new.md": b"new"}, set())
                for action in (sync.check_plan, lambda root, plan, hosts: sync.apply_plan(root, plan, hosts, "full")):
                    with self.assertRaises(ValueError):
                        action(target, plan, ["claude"])
                self.assertFalse((target / ".claude/new.md").exists())
                self.assertEqual(manifest.read_bytes(), before)

    def test_linked_worktree_sync_never_installs_hooks(self):
        source = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / ".git").write_text("gitdir: /outside/worktrees/test\n")
            before = (target / ".git").read_bytes()
            sync.apply_plan(target, sync.build_plan(["claude"], source, "full"), ["claude"], "full")
            self.assertEqual((target / ".git").read_bytes(), before)
            with self.assertRaises(SystemExit):
                sync.main(["--hooks"])

    def test_copied_skill_and_workflow_links_resolve_in_full_claude_sync(self):
        source_root = Path(__file__).parents[3]
        plan = sync.build_plan(["claude"], source_root, layout="full")
        with tempfile.TemporaryDirectory() as temp:
            target_root = Path(temp)
            sync.apply_plan(target_root, plan, ["claude"], "full")
            project_flow = (target_root / ".claude/skills/project-flow/SKILL.md").read_text()
            workflow_index = (target_root / ".claude/workflows/README.md").read_text()
            self.assertIn(".agents/rules/README.md", project_flow)
            self.assertIn(".agents/tools/README.md", workflow_index)
            for rel, content in plan.files.items():
                if not (rel.startswith(".claude/skills/") or rel.startswith(".claude/workflows/")) or not rel.endswith(".md"):
                    continue
                rendered_path = target_root / rel
                for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content.decode()):
                    if link.startswith(("#", "http://", "https://", "mailto:")):
                        continue
                    path = link.split("#", 1)[0].split("?", 1)[0]
                    resolved = source_root / path if path.startswith(".agents/") else rendered_path.parent / path
                    source_file = source_root / ".agents" / Path(rel.removeprefix(".claude/"))
                    source_target = (source_file.parent / path).resolve()
                    if path.startswith(".agents/") or source_target.exists():
                        self.assertTrue(resolved.exists(), f"{rel}: {link}")

    def test_copied_skills_omit_upstream_plugin_packaging(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            skill = source / ".agents/skills/demo"
            for rel in ("SKILL.md", ".claude-plugin/plugin.json", ".cursor-plugin/plugin.json",
                        ".github/workflows/ci.yml", "scripts/check.py"):
                (skill / rel).parent.mkdir(parents=True, exist_ok=True)
                (skill / rel).write_text("x\n", encoding="utf-8")
            files, _ = sync.collect_skill_tree(skill, ".claude/skills")
            self.assertEqual(
                sorted(files),
                [".claude/skills/demo/SKILL.md", ".claude/skills/demo/scripts/check.py"],
            )

    def test_sync_refuses_unmanaged_collision_and_has_no_external_target_option(self):
        root = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            direct_claude = project / ".claude"
            conflict = direct_claude / "skills/caveman/SKILL.md"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("custom user agent", encoding="utf-8")

            target_root = project
            plan = sync.build_plan(["claude"], root, layout="simple")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                sync.apply_plan(target_root, plan, ["claude"], "simple")
            self.assertEqual(conflict.read_text(encoding="utf-8"), "custom user agent")

    def test_sync_does_not_claim_identical_unmanaged_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / ".claude/agents/coordinator.md"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"same")
            sync.apply_plan(root, sync.SyncPlan({".claude/agents/coordinator.md": b"same"}, set()), ["claude"], "full")
            manifest = sync.manifest_path(root, ["claude"])
            self.assertEqual(sync.read_manifest(manifest), set())
            sync.apply_plan(root, sync.SyncPlan({}, set()), ["claude"], "simple")
            self.assertEqual(existing.read_bytes(), b"same")

    def test_sync_rejects_traversal_symlinks_and_unsafe_manifest_entries(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            escaped = Path(outside) / "secret"
            plan = sync.SyncPlan({"../secret": b"overwrite"}, set())
            with self.assertRaisesRegex(ValueError, "unsafe repository-relative"):
                sync.apply_plan(root, plan, ["claude"], "simple")
            self.assertFalse(escaped.exists())

            (root / ".claude").symlink_to(outside, target_is_directory=True)
            plan = sync.SyncPlan({".claude/agent.md": b"overwrite"}, set())
            with self.assertRaisesRegex(ValueError, "refusing symlink"):
                sync.apply_plan(root, plan, ["claude"], "simple")
            self.assertFalse((Path(outside) / "agent.md").exists())

    def test_sync_rejects_manifest_escape_before_deleting(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            escaped = Path(outside) / "keep"
            escaped.write_text("keep", encoding="utf-8")
            manifest = sync.manifest_path(root, ["claude"])
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '{"managed_files": ["../keep"]}', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsafe repository-relative"):
                sync.apply_plan(root, sync.SyncPlan({}, set()), ["claude"], "simple")
            self.assertEqual(escaped.read_text(encoding="utf-8"), "keep")

    def test_sync_rejects_external_target_and_removed_options(self):
        with self.assertRaises(SystemExit):
            sync.main(["--target", "/tmp/outside"])


if __name__ == "__main__":
    unittest.main()
