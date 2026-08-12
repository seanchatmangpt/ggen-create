from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ggen_create.cases import (
    parameterize_body,
    parameterize_body_many,
    replacements_for,
    replacements_for_many,
)
from ggen_create.model import GgenCreateError, MULTI_SEED_VERSION
from ggen_create.package import build_package, ontology_text, ontology_text_many
from ggen_create.session import (
    add_paths,
    add_seed,
    load_session,
    seeds_for_session,
    set_seed,
    start_session,
)


class MultiSeedBackCompatTests(unittest.TestCase):
    """Table-driven proof: with exactly one seed named "name", every _many
    function is byte-identical to its pre-Phase-2 single-seed counterpart --
    the back-compat guarantee product/PRD.md's "Infer -- Phase 2" section
    requires."""

    CASES = [
        ("plain word", "Hello world, this is HelloWorld again."),
        ("path-shaped text", "src/HelloWorld/HelloWorld.txt"),
        ("no occurrence", "nothing to see here"),
        ("empty text", ""),
    ]

    def test_replacements_for_many_matches_single_seed(self) -> None:
        for label, text in self.CASES:
            with self.subTest(label):
                single = replacements_for(text, "HelloWorld")
                many = replacements_for_many(text, [("name", "HelloWorld")])
                self.assertEqual(single, many)

    def test_parameterize_body_many_matches_single_seed(self) -> None:
        for label, text in self.CASES:
            with self.subTest(label):
                single = parameterize_body(text, "HelloWorld")
                many = parameterize_body_many(text, [("name", "HelloWorld")])
                self.assertEqual(single, many)

    def test_ontology_text_many_matches_single_seed(self) -> None:
        self.assertEqual(
            ontology_text("HelloWorld"),
            ontology_text_many([("name", "HelloWorld")]),
        )


class MultiSeedSessionTests(unittest.TestCase):
    def test_add_seed_migrates_version_and_seeds_seed_zero_from_primary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            set_seed(session, "HelloWorld")
            add_seed(session, "greeting", "Bonjour")

            document = load_session(session)
            self.assertEqual(document["hygen_create_version"], MULTI_SEED_VERSION)
            self.assertEqual(
                document["seeds"],
                [
                    {"name": "name", "value": "HelloWorld"},
                    {"name": "greeting", "value": "Bonjour"},
                ],
            )
            self.assertEqual(
                seeds_for_session(document),
                [("name", "HelloWorld"), ("greeting", "Bonjour")],
            )

    def test_add_seed_before_primary_seed_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            with self.assertRaisesRegex(
                GgenCreateError, "PRIMARY_SEED_REQUIRED_REFUSED"
            ):
                add_seed(session, "greeting", "Bonjour")

    def test_duplicate_seed_name_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            set_seed(session, "HelloWorld")
            add_seed(session, "greeting", "Bonjour")
            with self.assertRaisesRegex(
                GgenCreateError, "PARAMETER_SEED_NAME_COLLISION_REFUSED"
            ):
                add_seed(session, "greeting", "Ciao")

    def test_re_adding_the_reserved_name_seed_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            set_seed(session, "HelloWorld")
            add_seed(session, "greeting", "Bonjour")
            with self.assertRaisesRegex(
                GgenCreateError, "PARAMETER_SEED_NAME_COLLISION_REFUSED"
            ):
                add_seed(session, "name", "Something")

    def test_usename_after_migration_keeps_seeds_zero_in_sync(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            set_seed(session, "HelloWorld")
            add_seed(session, "greeting", "Bonjour")
            set_seed(session, "Goodbye")

            document = load_session(session)
            self.assertEqual(document["templatize_using_name"], "Goodbye")
            self.assertEqual(document["seeds"][0], {"name": "name", "value": "Goodbye"})
            self.assertEqual(document["seeds"][1], {"name": "greeting", "value": "Bonjour"})


class MultiSeedCollisionLawTests(unittest.TestCase):
    """Real, end-to-end proof: overlapping occurrences from two DIFFERENT
    seeds are refused, never silently resolved -- product/PRD.md's "Infer --
    Phase 2" requirement, proven against the real capture -> build_package
    pipeline, not just the internal cases.py scan."""

    def test_two_non_overlapping_seeds_coexist_in_a_real_package_build(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "greeter.txt").write_text(
                "HelloWorld says Bonjour to everyone.",
                encoding="utf-8",
            )
            session = start_session(root, "greeter")
            add_paths(session, ["greeter.txt"], cwd=root)
            set_seed(session, "HelloWorld")
            add_seed(session, "greeting", "Bonjour")

            result = build_package(session, root / "packages")
            self.assertTrue(result.package_dir.is_dir())

            ontology = (result.package_dir / "ontology.ttl").read_text(
                encoding="utf-8"
            )
            # The default "name" seed keeps its real, unprefixed predicates...
            self.assertIn("gc:capitalized", ontology)
            self.assertIn('"HelloWorld"', ontology)
            # ...and the second seed's own real, qualified predicates are present too.
            self.assertIn("gc:greeting_capitalized", ontology)
            self.assertIn('"Bonjour"', ontology)

            templates_dir = result.package_dir / "templates"
            rendered = next(templates_dir.glob("*.tmpl")).read_text(encoding="utf-8")
            self.assertIn("{{ row.capitalized }}", rendered)
            self.assertIn("{{ row.greeting_capitalized }}", rendered)

    def test_overlapping_seed_occurrences_are_refused_before_output_creation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            # "HelloWorld" is a strict prefix of "HelloWorldWide" -- both seeds'
            # literal forms match at the same starting position in this text, a
            # real, unavoidable overlap (not merely adjacent occurrences).
            (root / "greeter.txt").write_text(
                "HelloWorldWide is the plan.",
                encoding="utf-8",
            )
            session = start_session(root, "greeter")
            add_paths(session, ["greeter.txt"], cwd=root)
            set_seed(session, "HelloWorld")
            add_seed(session, "wide", "HelloWorldWide")

            output = root / "packages"
            with self.assertRaisesRegex(
                GgenCreateError, "PARAMETER_COLLISION_REFUSED"
            ):
                build_package(session, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
