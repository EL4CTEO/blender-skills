"""Host-only routing/install regression tests. No Blender or network needed.

Run: python -m unittest discover -s tests -p test_router_host.py -v
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


router = module("router", ROOT / "skills/blender-router/scripts/route.py")
installer = module("installer", ROOT / "tools/install_bundle.py")


class Routing(unittest.TestCase):
    def test_complete_coverage(self):
        names = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")} - {"blender-router"}
        self.assertEqual(names, {w["name"] for w in router.catalog()["workflows"]})
        for cmd in router.catalog()["commands"]:
            with self.subTest(command=cmd):
                result = router.run(command=cmd)
                self.assertEqual(result["status"], "routed")
                self.assertFalse(result["execution_performed"])
                self.assertEqual(result["stages"][0]["skill"], "blender-core")

    def test_production_request(self):
        result = router.run("Build a game-ready Blender crate for Unreal with baked normals and LODs")
        names = [s["skill"] for s in result["stages"]]
        for skill in ("hardsurface-modeling", "texture-baking", "game-optimization", "export-pipelines"):
            self.assertIn("blender-" + skill, names)
        self.assertLess(names.index("blender-retopology-uv"), names.index("blender-texture-baking"))
        self.assertIn("blender-pbr-materials", names)
        self.assertLess(names.index("blender-asset-qa"), names.index("blender-export-pipelines"))

    def test_existing_product_and_complete_character(self):
        result = router.run("Produce a cinematic Blender product turntable from an existing product mesh")
        names = [s["skill"] for s in result["stages"]]
        self.assertNotIn("blender-hardsurface-modeling", names)
        for skill in ("workflow-recipes", "pbr-materials", "lighting-lookdev", "rendering", "asset-qa"):
            self.assertIn("blender-" + skill, names)
        result = router.run("/blender plan rig this character, retarget a Mixamo walk, then export to Unity")
        self.assertIn("blender-workflow-recipes", [s["skill"] for s in result["stages"]])

    def test_negative_contexts(self):
        for prompt in ("Animate a CSS button", "Edit a portrait photo", "Buy a kitchen blender", "Don't use Blender; use CSS", "Write a sales email"):
            with self.subTest(prompt=prompt):
                self.assertEqual(router.run(prompt)["status"], "outside_scope")

    def test_manual_plan_and_alias(self):
        self.assertEqual(router.run("/blender plan a prop")["mode"], "plan")
        self.assertTrue(router.run("$blender-router inspect")["read_only"])
        self.assertEqual(router.run("/blender help")["status"], "help")
        with self.assertRaises(ValueError):
            router.run(command="nonexistent")

    def test_renamed_paths_and_missing_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skill-some-id"
            d.mkdir()
            (d / "SKILL.md").write_text("---\nname: blender-core\ndescription: core\n---\nCore", encoding="utf-8")
            self.assertEqual(router.run(command="inspect", skills_root=tmp)["status"], "routed")
            result = router.run(command="export", skills_root=tmp)
            self.assertEqual(result["status"], "missing_dependencies")
            self.assertIn("blender-export-pipelines", result["missing_dependencies"])


class Install(unittest.TestCase):
    def test_related_agents_use_role_not_incidental_body_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            agents = base / ".claude/agents"
            agents.mkdir(parents=True)
            for name, description, body in [
                ("artist", "3D technical artist using Blender", ""),
                ("director", "Executive Creative Director", ""),
                ("finance", "Finance adviser", "Do not use Blender"),
                ("voice", "Renders output in the right voice", ""),
                ("flat", "Animation and motion specialist, 2D only", "")]:
                (agents / (name + ".md")).write_text("---\ndescription: " + description + "\n---\n" + body, encoding="utf-8")
            names = {Path(p).stem for p in installer.related_bindings(base)}
            self.assertEqual(names, {"artist", "director"})

    def test_dry_run_idempotency_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            agent = base / "agents/artist.md"
            agent.parent.mkdir()
            original = b"---\r\nname: artist\r\n---\r\nKeep my identity.\r\n"
            agent.write_bytes(original)
            plan = installer.make_plan(base, ["all"], ["agents/artist.md"])
            self.assertFalse((base / ".claude").exists())
            self.assertEqual(len(plan["targets"]), 6)
            result = installer.apply_plan(plan)
            self.assertTrue(result["applied"])
            self.assertTrue(agent.read_bytes().startswith(original))
            self.assertEqual(agent.read_bytes().count(installer.BEGIN.encode()), 1)
            again = installer.make_plan(base, ["all"], ["agents/artist.md"])
            self.assertEqual(installer.summary(again)["files_to_change"], 0)
            self.assertTrue(any(p.read_bytes() == original for p in (base / ".blender-router-install/backups").rglob("*.bak")))

    def test_collisions_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            existing = base / ".agents/skills/blender-core/SKILL.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("my custom skill", encoding="utf-8")
            plan = installer.make_plan(base, ["codex"])
            self.assertTrue(plan["conflicts"])
            with self.assertRaises(ValueError):
                installer.apply_plan(plan)
            self.assertEqual(existing.read_text(), "my custom skill")

    def test_stale_plan_and_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            agent = base / "agent.md"
            agent.write_text("original", encoding="utf-8")
            plan = installer.make_plan(base, ["codex"], ["agent.md"])
            agent.write_text("user changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.apply_plan(plan)
            with self.assertRaises(ValueError):
                installer.make_plan(base, ["codex"], ["../outside.md"])


if __name__ == "__main__":
    unittest.main()
