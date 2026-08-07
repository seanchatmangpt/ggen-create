"""
Chicago-school JTBD acceptance tests for ggen-create v26.8.6.

Each case validates a user job from product/PRD.md through the public CLI
boundary. Tests observe filesystem and process consequences rather than
internal module state.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jtbd_support import (
    GreeterWorkspace,
    hola_reference_tree,
    run_create,
    write_bounded_fake_ggen,
    write_greeter_exemplar,
)


class CaptureJobTests(unittest.TestCase):
    """JTBD: pin an exemplar root, admit files, produce observation identity."""

    def test_developer_starts_greeter_and_receives_six_field_session(self) -> None:
        with GreeterWorkspace() as workspace:
            session = json.loads(workspace.session.read_text(encoding="utf-8"))
            self.assertEqual(
                list(session),
                [
                    "about",
                    "hygen_create_version",
                    "name",
                    "files_and_dirs",
                    "templatize_using_name",
                    "gen_parent_dir",
                ],
            )
            self.assertEqual(session["name"], "greeter")
            self.assertIn("ggen-create.json", session["files_and_dirs"])

    def test_developer_admits_only_explicit_utf8_files(self) -> None:
        with GreeterWorkspace() as workspace:
            outcome = workspace.run("status", json_output=True)
            self.assertEqual(outcome.exit_code, 0, outcome.stderr)
            paths = {item["path"] for item in outcome.json["files"]}
            self.assertEqual(paths, {"ggen-create.json", "package.json", "dist/hello.js"})

    def test_developer_is_refused_when_adding_outside_capture_root(self) -> None:
        with GreeterWorkspace() as workspace:
            outside = workspace.root.parent / "outside.txt"
            outside.write_text("nope\n", encoding="utf-8")
            outcome = run_create(workspace.root, "add", str(outside))
            self.assertEqual(outcome.exit_code, 2)
            self.assertTrue(outcome.refused("PATH_OUTSIDE_CAPTURE_ROOT_REFUSED"))


class InferJobTests(unittest.TestCase):
    """JTBD: derive lexical transforms from a single seed."""

    def test_developer_seeds_hello_and_status_exposes_case_family(self) -> None:
        with GreeterWorkspace() as workspace:
            outcome = workspace.run("status", json_output=True)
            self.assertEqual(outcome.exit_code, 0, outcome.stderr)
            report = outcome.json
            self.assertEqual(report["seed"], "Hello")
            self.assertGreater(report["replacement_count"], 0)
            all_variables: set[str] = set()
            for file_info in report["files"]:
                for replacement in (
                    file_info["path_replacements"] + file_info["content_replacements"]
                ):
                    all_variables.add(replacement["variable"])
            self.assertTrue({"lower", "capitalized"}.issubset(all_variables))

    def test_native_parameter_alias_matches_usename(self) -> None:
        with GreeterWorkspace() as workspace:
            outcome = workspace.run("parameter", "seed", "Hello", json_output=True)
            self.assertEqual(outcome.exit_code, 0, outcome.stderr)
            status = workspace.run("status", json_output=True)
            self.assertEqual(status.json["seed"], "Hello")


class InspectJobTests(unittest.TestCase):
    """JTBD: preview correspondences before any package emission."""

    def test_status_is_side_effect_free_until_generate(self) -> None:
        with GreeterWorkspace() as workspace:
            packages = workspace.package_root()
            outcome = workspace.run("status", "-v")
            self.assertEqual(outcome.exit_code, 0, outcome.stderr)
            self.assertFalse(packages.exists())
            self.assertIn("dist/hello.js", outcome.stdout)
            self.assertIn("replacements", outcome.stdout.lower())

    def test_status_reports_parameterized_target_paths(self) -> None:
        with GreeterWorkspace() as workspace:
            outcome = workspace.run("status", json_output=True)
            hello = next(
                item for item in outcome.json["files"] if item["path"] == "dist/hello.js"
            )
            self.assertEqual(hello["target_template"], "dist/{{ row.lower }}.js")
            self.assertGreater(len(hello["path_replacements"]), 0)


class PackageJobTests(unittest.TestCase):
    """JTBD: emit a ggen-consumable factory with revision law."""

    REQUIRED_PACKAGE_FILES = (
        "ggen.toml",
        "ontology.ttl",
        "ggen-create-package.json",
        "receipt.json",
    )

    def test_pack_author_receives_complete_factory_layout(self) -> None:
        with GreeterWorkspace() as workspace:
            built = workspace.run(
                "generate",
                "--output",
                str(workspace.package_root()),
                json_output=True,
            )
            self.assertEqual(built.exit_code, 0, built.stderr)
            package = Path(built.json["package"])
            for name in self.REQUIRED_PACKAGE_FILES:
                self.assertTrue((package / name).is_file(), name)
            templates = list((package / "templates").glob("*.tmpl"))
            self.assertEqual(len(templates), 3)

    def test_identical_rerun_reports_no_changed_revision(self) -> None:
        with GreeterWorkspace() as workspace:
            output = str(workspace.package_root())
            first = workspace.run("generate", "--output", output, json_output=True)
            second = workspace.run("generate", "--output", output, json_output=True)
            self.assertTrue(first.json["changed"])
            self.assertFalse(second.json["changed"])
            self.assertIsNone(second.json["archived_previous"])

    def test_changed_exemplar_archives_prior_factory(self) -> None:
        with GreeterWorkspace() as workspace:
            output = workspace.package_root()
            workspace.run("generate", "--output", str(output), json_output=True)
            (workspace.root / "dist/hello.js").write_text(
                'console.log("Hello!!")\n',
                encoding="utf-8",
            )
            rebuilt = workspace.run("generate", "--output", str(output), json_output=True)
            self.assertTrue(rebuilt.json["changed"])
            archive = Path(rebuilt.json["archived_previous"])
            self.assertEqual(archive.name, "greeter.1")
            self.assertTrue(archive.is_dir())


class VerifyJobTests(unittest.TestCase):
    """JTBD: reconstruct exemplars, vary parameters, and issue receipts."""

    def test_developer_compares_byte_identical_trees(self) -> None:
        with GreeterWorkspace() as workspace:
            with tempfile.TemporaryDirectory() as outer:
                left = Path(outer) / "left"
                right = Path(outer) / "right"
                for target in (left, right):
                    (target / "dist").mkdir(parents=True)
                    shutil.copy2(
                        workspace.root / "package.json",
                        target / "package.json",
                    )
                    shutil.copy2(
                        workspace.root / "dist/hello.js",
                        target / "dist/hello.js",
                    )
                outcome = run_create(left.parent, "compare", str(left), str(right), json_output=True)
                self.assertEqual(outcome.exit_code, 0, outcome.stderr)
                self.assertTrue(outcome.json["equal"])

    def test_developer_verifies_hola_variation_with_bounded_manufacturer(self) -> None:
        with GreeterWorkspace() as workspace:
            output = workspace.package_root()
            workspace.run("generate", "--output", str(output), json_output=True)
            fake = workspace.root / "fake-ggen"
            write_bounded_fake_ggen(fake)
            reference = hola_reference_tree(workspace.root, workspace.session)
            report = workspace.run(
                "verify",
                "--output",
                str(workspace.root / "verify"),
                "--ggen-bin",
                str(fake),
                "--set",
                "Hola",
                "--reference-dir",
                str(reference),
                "--reference-id",
                "ronp001/hygen-create@test",
                json_output=True,
            )
            self.assertEqual(report.exit_code, 0, report.stderr)
            payload = report.json
            self.assertEqual(payload["checkpoints"]["P6_REVISION_PARITY"], "ALIVE")
            self.assertEqual(payload["checkpoints"]["P7_PARITY_CROWN"], "ALIVE")
            self.assertTrue(payload["reference_comparison"]["equal"])


class ApplicationDeveloperJourneyTests(unittest.TestCase):
    """End-to-end job: turn a repeated greeter into a reusable factory."""

    def test_full_hygen_compatible_cli_journey(self) -> None:
        with GreeterWorkspace() as workspace:
            steps = [
                workspace.run("status", json_output=True),
                workspace.run(
                    "generate",
                    "--output",
                    str(workspace.package_root()),
                    json_output=True,
                ),
            ]
            for step in steps:
                self.assertEqual(step.exit_code, 0, step.stderr)
            package = Path(steps[1].json["package"])
            self.assertTrue((package / "receipt.json").is_file())
            replay = workspace.run(
                "generate",
                "--output",
                str(workspace.package_root()),
                json_output=True,
            )
            self.assertFalse(replay.json["changed"])


if __name__ == "__main__":
    unittest.main()
