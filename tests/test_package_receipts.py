from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.integrity import verify_package
from ggen_create.model import GgenCreateError
from ggen_create.package import build_package, rewrite_package_parameter
from ggen_create.session import add_paths, set_seed, start_session


class PackageReceiptTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        (root / "Hello.txt").write_text(
            "Hello hello HELLO",
            encoding="utf-8",
        )
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        package = build_package(session, root / "packages").package_dir
        return session, package

    @staticmethod
    def manifest(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_build_receipt_is_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            integrity = verify_package(package)
            self.assertTrue(integrity["valid"], integrity)
            self.assertTrue(integrity["receipt_valid"], integrity)
            self.assertEqual(integrity["operation"], "package-build")
            self.assertEqual(integrity["parameter_value"], "Hello")
            self.assertIsNone(integrity["parent"])
            self.assertEqual(
                integrity["claimed_receipt_digest"],
                integrity["computed_receipt_digest"],
            )
            metadata = json.loads(
                (package / "ggen-create-package.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(metadata["schema"], "ggen-create-package/0.2")
            self.assertNotIn("source_root", metadata)

    def test_identical_exemplars_are_byte_identical_across_roots(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
        ):
            _, left = self.fixture(Path(left_raw))
            _, right = self.fixture(Path(right_raw))
            self.assertEqual(self.manifest(left), self.manifest(right))
            left_receipt = json.loads(
                (left / "receipt.json").read_text(encoding="utf-8")
            )
            right_receipt = json.loads(
                (right / "receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                left_receipt["receipt_digest"],
                right_receipt["receipt_digest"],
            )

    def test_parameter_rewrite_emits_successor_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            before = json.loads(
                (package / "receipt.json").read_text(encoding="utf-8")
            )
            result = rewrite_package_parameter(package, "Hola")
            after = json.loads(
                (package / "receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["parent"], before["receipt_digest"])
            self.assertEqual(after["parent"], before["receipt_digest"])
            self.assertNotEqual(
                after["receipt_digest"],
                before["receipt_digest"],
            )
            self.assertEqual(after["operation"], "parameter-rewrite")
            self.assertEqual(after["parameter_value"], "Hola")
            self.assertIn(
                'gc:name "Hola"',
                (package / "ontology.ttl").read_text(encoding="utf-8"),
            )
            metadata = json.loads(
                (package / "ggen-create-package.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(metadata["parameter"]["value"], "Hola")
            integrity = verify_package(package)
            self.assertTrue(integrity["valid"], integrity)

    def test_execution_integrity_allows_only_extra_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            (package / "generated.txt").write_text(
                "artifact",
                encoding="utf-8",
            )
            strict = verify_package(package)
            execution = verify_package(package, allow_extra=True)
            self.assertFalse(strict["valid"])
            self.assertEqual(strict["extra"], ["generated.txt"])
            self.assertTrue(execution["valid"], execution)
            self.assertEqual(execution["extra"], ["generated.txt"])

            (package / "ontology.ttl").write_text(
                "tampered",
                encoding="utf-8",
            )
            corrupted = verify_package(package, allow_extra=True)
            self.assertFalse(corrupted["valid"])
            self.assertIn("ontology.ttl", corrupted["different"])

    def test_tampering_after_rewrite_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            rewrite_package_parameter(package, "Hola")
            (package / "ontology.ttl").write_text(
                "tampered",
                encoding="utf-8",
            )
            integrity = verify_package(package)
            self.assertFalse(integrity["valid"])
            self.assertIn("ontology.ttl", integrity["different"])

    def test_rewrite_refuses_corrupted_precondition(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            (package / "ggen.toml").write_text(
                "corrupted",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "PACKAGE_INTEGRITY_REFUSED",
            ):
                rewrite_package_parameter(package, "Hola")

    def test_receipt_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, package = self.fixture(Path(raw))
            receipt_path = package / "receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["operation"] = "dishonest-operation"
            receipt_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            integrity = verify_package(package)
            self.assertFalse(integrity["valid"])
            self.assertFalse(integrity["receipt_valid"])


if __name__ == "__main__":
    unittest.main()
