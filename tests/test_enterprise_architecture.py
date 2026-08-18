from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import enterprise_architecture_check as eac


class EnterpriseArchitectureTests(unittest.TestCase):
    def test_repository_contract_is_alive(self) -> None:
        receipt = eac.evaluate(ROOT)
        failures = [check for check in receipt["checks"] if not check["passed"]]
        self.assertEqual(failures, [], failures)
        self.assertEqual(receipt["standing"], "ALIVE")

    def test_ambient_process_authority_breaks_standing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "architecture").mkdir()
            (root / "docs").mkdir()
            (root / "crates" / "ggen-dspy" / "src").mkdir(parents=True)
            for rel in (
                "architecture/ARD.md",
                "architecture/ADR-0001-RUST-DSPY-AUTHORITY.md",
                "architecture/ENTERPRISE_ARCHITECTURE.md",
                "docs/ENTERPRISE_READINESS.md",
            ):
                (root / rel).write_text("fixture\n", encoding="utf-8")
            (root / "Cargo.lock").write_text("# fixture\n", encoding="utf-8")
            (root / "rust-toolchain.toml").write_text(
                '[toolchain]\nchannel = "1.85.1"\n', encoding="utf-8"
            )
            (root / "crates" / "ggen-dspy" / "Cargo.toml").write_text(
                "[package]\nname = \"ggen-dspy\"\nversion = \"1.0.0\"\n"
                "publish = false\n\n[dependencies]\n",
                encoding="utf-8",
            )
            (root / "crates" / "ggen-dspy" / "src" / "lib.rs").write_text(
                "#![forbid(unsafe_code)]\n"
                "// ActionIntent CodeIntent ToolObservation REFUSED:ACTUATION_REQUIRES_BROKER\n"
                "fn forbidden() { let _ = std::process::Command::new(\"echo\"); }\n",
                encoding="utf-8",
            )
            (root / "architecture" / "enterprise.toml").write_text(
                (ROOT / "architecture" / "enterprise.toml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            receipt = eac.evaluate(root)
            self.assertEqual(receipt["standing"], "BUILD_BROKEN")
            ambient = next(check for check in receipt["checks"] if check["id"] == "ambient_authority")
            self.assertFalse(ambient["passed"])
            self.assertIn("std::process::", ambient["detail"])


if __name__ == "__main__":
    unittest.main()
