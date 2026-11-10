from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.cutover import PREFLIGHT_REFUSALS, PREREQS, STATE, TARGETS, TARGETS_SCHEMA
from ggen_create.model import GgenCreateError
from ggen_create.skills import Broker, SkillRegistry

OLD = "http://localhost:4000"
NEW = "http://localhost:3000"


def subject(root: Path, **over: bool) -> None:
    value = {k: True for k in PREFLIGHT_REFUSALS}
    value.update(over)
    (root / PREREQS).write_text(json.dumps(value), encoding="utf-8")
    (root / "fe").mkdir(exist_ok=True)
    (root / "fe" / ".env").write_text(
        f"A=1\nVITE_BACKEND_ORIGIN={OLD}\n# keep me\nexport VITE_X_URL={OLD}  \n", encoding="utf-8")
    (root / TARGETS).write_text(json.dumps({
        "schema": TARGETS_SCHEMA,
        "predecessors": ["xaas"],
        "targets": [
            {"file": "fe/.env", "key": "VITE_BACKEND_ORIGIN", "from": OLD, "to": NEW},
            {"file": "fe/.env", "key": "VITE_X_URL", "from": OLD, "to": NEW},
        ],
    }), encoding="utf-8")


def run(root: Path, skill: str, confirm: bool = False, **args):
    return Broker(root).execute(SkillRegistry().plan(skill, args), confirm=confirm)


class CutoverTests(unittest.TestCase):
    def test_preflight_refuses_each_unmet_prerequisite_with_typed_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for key, code in PREFLIGHT_REFUSALS.items():
                subject(root, **{key: False})
                with self.assertRaises(GgenCreateError) as caught:
                    run(root, "cutover.plan")
                self.assertEqual(caught.exception.code, code)

    def test_plan_is_deterministic_writes_nothing_and_refuses_value_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subject(root)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            a = run(root, "cutover.plan")["result"]
            b = run(root, "cutover.plan")["result"]
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})
            (root / "fe" / ".env").write_text("VITE_BACKEND_ORIGIN=http://elsewhere\nVITE_X_URL=" + OLD)
            with self.assertRaises(GgenCreateError) as caught:
                run(root, "cutover.plan")
            self.assertEqual(caught.exception.code, "TARGET_VALUE_MISMATCH_REFUSED")

    def test_power_rollback_is_byte_exact_and_refuses_drift_and_partial_flip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subject(root)
            env = root / "fe" / ".env"
            original = env.read_bytes()
            with self.assertRaises(GgenCreateError) as blocked:
                run(root, "cutover.power")
            self.assertEqual(blocked.exception.code, "ACTUATION_CONFIRMATION_REQUIRED_REFUSED")
            self.assertEqual(env.read_bytes(), original)

            run(root, "cutover.power", confirm=True)
            flipped = env.read_text()
            self.assertIn(f"VITE_BACKEND_ORIGIN={NEW}\n", flipped)
            self.assertIn(f"export VITE_X_URL={NEW}  \n", flipped)
            self.assertIn("# keep me\n", flipped)
            self.assertTrue(run(root, "cutover.verify", replay=True)["result"]["rollback_available"])
            with self.assertRaises(GgenCreateError) as twice:
                run(root, "cutover.power", confirm=True)
            self.assertEqual(twice.exception.code, "ALREADY_POWERED_REFUSED")

            env.write_text(flipped + "# edited after power\n")
            with self.assertRaises(GgenCreateError) as drift:
                run(root, "cutover.rollback", confirm=True)
            self.assertEqual(drift.exception.code, "TARGET_DRIFT_REFUSED")
            with self.assertRaises(GgenCreateError) as replay:
                run(root, "cutover.verify", replay=True)
            self.assertEqual(replay.exception.code, "REPLAY_DRIFT_REFUSED")

            env.write_text(flipped)
            run(root, "cutover.rollback", confirm=True)
            self.assertEqual(env.read_bytes(), original)
            self.assertEqual(json.loads((root / "cutover" / STATE).read_text())["active"], "legacy")

            # all-or-nothing: second target mismatches, so the first must stay untouched
            env.write_text(f"VITE_BACKEND_ORIGIN={OLD}\nVITE_X_URL=http://other\n")
            snapshot = env.read_bytes()
            with self.assertRaises(GgenCreateError):
                run(root, "cutover.power", confirm=True)
            self.assertEqual(env.read_bytes(), snapshot)

    def test_receipt_chain_verifies_after_sequence_including_a_failed_power(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subject(root)
            run(root, "cutover.plan")
            run(root, "cutover.power", confirm=True)
            run(root, "cutover.verify", replay=True)
            run(root, "cutover.rollback", confirm=True)
            subject(root, release_admitted=False)
            with self.assertRaises(GgenCreateError):
                run(root, "cutover.power", confirm=True)
            chain = run(root, "receipt.chain.verify")["result"]
            self.assertEqual(chain.get("valid"), True)
            states = [r.get("state") for r in __import__("ggen_create.runtime", fromlist=["x"])
                      .ReceiptStore(root).list()]
            self.assertIn("BLOCKED", states)
            self.assertEqual(states.count("PARTIAL_ALIVE"), 2)

    def test_cli_drives_the_whole_sequence_from_a_foreign_cwd(self) -> None:
        import contextlib
        import io
        import os

        from ggen_create.cli import run as cli

        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(raw)
            subject(root)
            env = root / "fe" / ".env"
            original = env.read_bytes()
            base = ["--json", "cutover"]
            sub = ["--subject-root", str(root)]
            cwd = os.getcwd()
            os.chdir(elsewhere)
            try:
                def go(*argv: str) -> int:
                    with contextlib.redirect_stdout(io.StringIO()):
                        return cli([*base, *argv])

                self.assertEqual(go("plan", *sub), 0)
                with self.assertRaises(GgenCreateError) as blocked:
                    go("power", *sub)
                self.assertEqual(blocked.exception.code, "ACTUATION_CONFIRMATION_REQUIRED_REFUSED")
                self.assertEqual(go("power", *sub, "--confirm"), 0)
                self.assertIn(NEW, env.read_text())
                self.assertEqual(go("verify", *sub, "--replay"), 0)
                self.assertEqual(go("rollback", *sub, "--confirm"), 0)
            finally:
                os.chdir(cwd)
            self.assertEqual(env.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
