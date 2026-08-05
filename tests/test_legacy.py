from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ggen_create.legacy import (
    build_legacy_bundle,
    plan_legacy_factory,
    verify_legacy_bundle,
)
from ggen_create.model import GgenCreateError
from ggen_create.skills import Broker, SkillRegistry

PRODUCER_COMMIT = "2d2b4aecc392a124e4fbeef0d1eb4b9b2642b3be"


class LegacyTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        (root / "AGENTS.md").write_text("# law\n", encoding="utf-8")
        (root / "RELEASE_CONTROL.md").write_text("# release\n", encoding="utf-8")
        (root / "ggen.toml").write_text(
            "[project]\nname=\"retail\"\n",
            encoding="utf-8",
        )
        (root / "src").mkdir()
        (root / "src" / "pricing.py").write_text(
            "def price(qty): return qty * 7\n",
            encoding="utf-8",
        )
        (root / "tests").mkdir()
        (root / "tests" / "test_pricing.py").write_text(
            "def test_price(): assert 1\n",
            encoding="utf-8",
        )
        (root / "ontology").mkdir()
        (root / "ontology" / "domain.ttl").write_text(
            "@prefix ex: <https://example/> .\n",
            encoding="utf-8",
        )
        (root / "schemas").mkdir()
        (root / "schemas" / "order.schema.json").write_text(
            "{}\n",
            encoding="utf-8",
        )

    def build(self, root: Path, output: Path, **kwargs: object):
        return build_legacy_bundle(
            root,
            output,
            producer_commit=PRODUCER_COMMIT,
            **kwargs,
        )

    def test_plan_is_deterministic_and_classified(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            arguments = {
                "output_root": root / "foundry/generated/intake",
                "program_id": "Fortune 5 Retail",
                "producer_commit": PRODUCER_COMMIT,
            }
            first = plan_legacy_factory(root, **arguments)
            second = plan_legacy_factory(root, **arguments)
            self.assertEqual(first, second)
            self.assertEqual(first["program_id"], "fortune-5-retail")
            self.assertEqual(first["standing"], "PARTIAL_ALIVE")
            self.assertEqual(first["classification_counts"]["source"], 1)
            self.assertEqual(first["classification_counts"]["test"], 1)
            self.assertEqual(first["blockers"], [])
            self.assertEqual(first["producer_identity"]["commit"], PRODUCER_COMMIT)

    def test_power_is_receipted_verified_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "foundry/generated/intake"
            first = self.build(root, output, program_id="retail-orders")
            self.assertTrue(first.changed)
            self.assertTrue(verify_legacy_bundle(output, subject_root=root)["valid"])
            receipt = json.loads((output / "receipt.json").read_text())
            self.assertEqual(receipt["producer_identity"]["commit"], PRODUCER_COMMIT)
            self.assertEqual(set(receipt["outputs"]), set(receipt["output_modes"]))
            second = self.build(root, output, program_id="retail-orders")
            self.assertFalse(second.changed)
            self.assertEqual(first.bundle_digest, second.bundle_digest)
            verify = subprocess.run(
                [
                    sys.executable,
                    str(output / "verify_bundle.py"),
                    str(output),
                    "--subject",
                    str(root),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)
            replay = subprocess.run(
                [
                    sys.executable,
                    str(output / "replay_bundle.py"),
                    str(output),
                    "--subject",
                    str(root),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout)

    def test_content_drift_is_build_broken(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            self.build(root, output)
            (root / "src" / "pricing.py").write_text(
                "def price(qty): return qty * 8\n",
                encoding="utf-8",
            )
            report = verify_legacy_bundle(output, subject_root=root)
            self.assertFalse(report["valid"])
            self.assertEqual(report["state"], "BUILD_BROKEN")
            self.assertIn(
                {"path": "src/pricing.py", "reason": "digest"},
                report["drift"],
            )

    def test_unadmitted_file_is_build_broken(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            self.build(root, output)
            (root / "src" / "ambient.py").write_text("pass\n", encoding="utf-8")
            report = verify_legacy_bundle(output, subject_root=root)
            self.assertFalse(report["valid"])
            self.assertIn(
                {"path": "src/ambient.py", "reason": "unadmitted"},
                report["drift"],
            )

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics")
    def test_source_mode_drift_is_build_broken(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            source = root / "src" / "pricing.py"
            source.chmod(0o644)
            output = root / "intake"
            self.build(root, output)
            source.chmod(0o755)
            report = verify_legacy_bundle(output, subject_root=root)
            self.assertFalse(report["valid"])
            self.assertIn(
                {"path": "src/pricing.py", "reason": "mode"},
                report["drift"],
            )

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics")
    def test_output_mode_tamper_is_build_broken(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            self.build(root, output)
            (output / "verify_bundle.py").chmod(0o644)
            report = verify_legacy_bundle(output, subject_root=root)
            self.assertFalse(report["valid"])
            self.assertFalse(report["checks"]["output_modes"])

    def test_existing_different_output_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            output.mkdir()
            (output / "foreign").write_text("x", encoding="utf-8")
            with self.assertRaises(GgenCreateError) as caught:
                self.build(root, output)
            self.assertEqual(caught.exception.code, "LEGACY_OUTPUT_EXISTS_REFUSED")
            self.assertTrue(self.build(root, output, force=True).changed)

    def test_symlink_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as outside:
            root = Path(raw)
            self.fixture(root)
            try:
                (root / "escape").symlink_to(Path(outside))
            except OSError:
                self.skipTest("symlink unavailable")
            with self.assertRaises(GgenCreateError) as caught:
                plan_legacy_factory(root)
            self.assertEqual(caught.exception.code, "SYMLINK_DIRECTORY_REFUSED")

    @unittest.skipIf(os.name == "nt" or not hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_special_file_is_refused_without_reading(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            os.mkfifo(root / "events.pipe")
            with self.assertRaises(GgenCreateError) as caught:
                plan_legacy_factory(root)
            self.assertEqual(caught.exception.code, "SPECIAL_FILE_REFUSED")

    def test_bounds_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            with self.assertRaises(GgenCreateError) as caught:
                plan_legacy_factory(root, max_files=1)
            self.assertEqual(caught.exception.code, "FILE_COUNT_BOUND_REFUSED")

    def test_broker_requires_confirmation_and_receipts_power(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            registry = SkillRegistry()
            broker = Broker(root)
            intent = registry.plan(
                "legacy.power",
                {
                    "subject_root": ".",
                    "output_root": "foundry/generated/intake",
                    "program_id": "fortune5-retail",
                },
            )
            with self.assertRaises(GgenCreateError) as blocked:
                broker.execute(intent)
            self.assertEqual(
                blocked.exception.code,
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
            )
            result = broker.execute(intent, confirm=True)
            self.assertEqual(result["state"], "PARTIAL_ALIVE")
            self.assertTrue(Path(result["result"]["receipt"]).is_file())
            self.assertTrue(result["receipt"]["receipt_digest"].startswith("sha256:"))
            verified = broker.execute(
                registry.plan(
                    "legacy.verify",
                    {
                        "bundle_root": "foundry/generated/intake",
                        "subject_root": ".",
                    },
                )
            )
            self.assertEqual(verified["state"], "ALIVE")


if __name__ == "__main__":
    unittest.main()
