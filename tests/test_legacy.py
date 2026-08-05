from __future__ import annotations

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

    def test_plan_is_deterministic_and_classified(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            arguments = {
                "output_root": root / "foundry/generated/intake",
                "program_id": "Fortune 5 Retail",
            }
            first = plan_legacy_factory(root, **arguments)
            second = plan_legacy_factory(root, **arguments)
            self.assertEqual(first, second)
            self.assertEqual(first["program_id"], "fortune-5-retail")
            self.assertEqual(first["standing"], "PARTIAL_ALIVE")
            self.assertEqual(first["classification_counts"]["source"], 1)
            self.assertEqual(first["classification_counts"]["test"], 1)
            self.assertEqual(first["blockers"], [])

    def test_power_is_receipted_verified_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "foundry/generated/intake"
            first = build_legacy_bundle(
                root,
                output,
                program_id="retail-orders",
            )
            self.assertTrue(first.changed)
            self.assertTrue(
                verify_legacy_bundle(output, subject_root=root)["valid"]
            )
            second = build_legacy_bundle(
                root,
                output,
                program_id="retail-orders",
            )
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

    def test_drift_is_build_broken(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            build_legacy_bundle(root, output)
            (root / "src" / "pricing.py").write_text(
                "def price(qty): return qty * 8\n",
                encoding="utf-8",
            )
            report = verify_legacy_bundle(output, subject_root=root)
            self.assertFalse(report["valid"])
            self.assertEqual(report["state"], "BUILD_BROKEN")
            self.assertEqual(report["drift"][0]["reason"], "digest")

    def test_existing_different_output_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            output = root / "intake"
            output.mkdir()
            (output / "foreign").write_text("x", encoding="utf-8")
            with self.assertRaises(GgenCreateError) as caught:
                build_legacy_bundle(root, output)
            self.assertEqual(
                caught.exception.code,
                "LEGACY_OUTPUT_EXISTS_REFUSED",
            )
            self.assertTrue(build_legacy_bundle(root, output, force=True).changed)

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
            self.assertEqual(
                caught.exception.code,
                "SYMLINK_DIRECTORY_REFUSED",
            )

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
            self.assertTrue(
                result["receipt"]["receipt_digest"].startswith("sha256:")
            )
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
