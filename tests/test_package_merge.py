from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ggen_create.package import build_package
from ggen_create.session import add_paths, set_seed, start_session


class PackageMergeTests(unittest.TestCase):
    def fixture_session(self, root: Path) -> Path:
        (root / "Hello.txt").write_text(
            "Hello hello HELLO",
            encoding="utf-8",
        )
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        return session

    def test_merge_true_into_existing_pack_appends_ontology_and_preserves_manifests(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture_session(root)
            packages_dir = root / "packages"
            target = packages_dir / "greeter"
            target.mkdir(parents=True)

            existing_ontology = (
                "@prefix ex: <urn:example:> .\n\nex:Thing a ex:Widget .\n"
            )
            (target / "ontology.ttl").write_text(
                existing_ontology,
                encoding="utf-8",
            )
            existing_ggen_toml = "[project]\nname = \"pre-existing\"\n"
            (target / "ggen.toml").write_text(
                existing_ggen_toml,
                encoding="utf-8",
            )
            existing_pack_toml = "[pack]\nname = \"greeter\"\n"
            (target / "pack.toml").write_text(
                existing_pack_toml,
                encoding="utf-8",
            )

            result = build_package(session, packages_dir, merge=True)

            self.assertEqual(result.package_dir, target)

            ontology_text = (target / "ontology.ttl").read_text(
                encoding="utf-8"
            )
            self.assertIn("ex:Thing a ex:Widget .", ontology_text)
            self.assertIn("gc:subject", ontology_text)

            self.assertEqual(
                (target / "ggen.toml").read_text(encoding="utf-8"),
                existing_ggen_toml,
            )
            self.assertEqual(
                (target / "pack.toml").read_text(encoding="utf-8"),
                existing_pack_toml,
            )

            templates_dir = target / "templates"
            self.assertTrue(templates_dir.is_dir())
            tmpl_files = list(templates_dir.glob("*.tmpl"))
            self.assertTrue(tmpl_files)

            self.assertTrue((target / "ggen-create-package.json").is_file())
            self.assertTrue((target / "receipt.json").is_file())

    def test_merge_false_default_behavior_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture_session(root)
            packages_dir = root / "packages"
            target = packages_dir / "greeter"
            target.mkdir(parents=True)
            (target / "ontology.ttl").write_text(
                "@prefix ex: <urn:example:> .\n\nex:Thing a ex:Widget .\n",
                encoding="utf-8",
            )
            (target / "ggen.toml").write_text(
                "[project]\nname = \"pre-existing\"\n",
                encoding="utf-8",
            )
            (target / "stray.txt").write_text("keepme?", encoding="utf-8")

            result = build_package(session, packages_dir)

            self.assertTrue(result.changed)
            self.assertIsNotNone(result.archived_previous)
            self.assertTrue(result.archived_previous.is_dir())
            self.assertTrue((result.archived_previous / "stray.txt").is_file())

            ontology_text = (target / "ontology.ttl").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("ex:Thing", ontology_text)
            self.assertIn("gc:subject", ontology_text)
            self.assertFalse((target / "stray.txt").exists())

    def test_merge_true_on_nonexistent_target_behaves_like_fresh_build(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture_session(root)
            packages_dir = root / "packages"
            target = packages_dir / "greeter"

            result = build_package(session, packages_dir, merge=True)

            self.assertTrue(result.changed)
            self.assertEqual(result.package_dir, target)
            self.assertTrue((target / "ontology.ttl").is_file())
            self.assertTrue((target / "ggen.toml").is_file())
            self.assertTrue((target / "ggen-create-package.json").is_file())
            self.assertTrue((target / "receipt.json").is_file())
            ontology_text = (target / "ontology.ttl").read_text(
                encoding="utf-8"
            )
            self.assertIn("gc:subject", ontology_text)


if __name__ == "__main__":
    unittest.main()
