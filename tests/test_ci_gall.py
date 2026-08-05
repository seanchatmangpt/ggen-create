from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gall_checkpoint import (
    CHECKPOINTS,
    CheckpointFailure,
    Context,
    _sample_receipt,
    _scan_build,
    _scan_docs,
    _scan_ontology,
    _validate_receipt,
    execute_checkpoint,
)


class GallContractTests(unittest.TestCase):
    def test_registry_is_closed_and_ordered(self):
        self.assertEqual(
            CHECKPOINTS,
            ("exact_head", "clean_tree", "routing", "ci", "docs", "ontology", "build", "receipt"),
        )

    def test_receipt_requires_candidate_admitted_alive_transition(self):
        receipt = _sample_receipt("a" * 40)
        self.assertEqual(_validate_receipt(receipt)["transition"], ["CANDIDATE", "ADMITTED", "ALIVE"])

    def test_receipt_cannot_begin_alive(self):
        receipt = _sample_receipt("a" * 40)
        receipt["transitions"] = ["ALIVE"]
        with self.assertRaises(CheckpointFailure) as caught:
            _validate_receipt(receipt)
        self.assertEqual(caught.exception.code, "BUILD_BROKEN:ILLEGAL_STANDING_TRANSITION")

    def test_receipt_requires_negative_falsifier(self):
        receipt = _sample_receipt("a" * 40)
        receipt["negative_falsifier"]["passed"] = False
        with self.assertRaises(CheckpointFailure) as caught:
            _validate_receipt(receipt)
        self.assertEqual(caught.exception.code, "BUILD_BROKEN:NEGATIVE_FALSIFIER_MISSING")

    def test_receipt_requires_replay(self):
        receipt = _sample_receipt("a" * 40)
        receipt["replay"]["match"] = False
        with self.assertRaises(CheckpointFailure) as caught:
            _validate_receipt(receipt)
        self.assertEqual(caught.exception.code, "BUILD_BROKEN:REPLAY_MISSING")

    def test_docs_positive_and_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "README.md").write_text("# repo\n", encoding="utf-8")
            (root / "BOOTSTRAP.md").write_text("bootstrap\n", encoding="utf-8")
            (root / "docs" / "proof.md").write_text("# proof\n", encoding="utf-8")
            self.assertEqual(_scan_docs(root)["count"], 3)
            (root / "docs" / "proof.md").write_text("", encoding="utf-8")
            with self.assertRaises(CheckpointFailure):
                _scan_docs(root)

    def test_ontology_bootstrap_absence_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ontology").mkdir()
            (root / "ontology" / ".keep").write_text("", encoding="utf-8")
            observation = _scan_ontology(root)
            self.assertTrue(observation["bootstrap_empty_surface"])
            self.assertEqual(observation["substantive_count"], 0)

    def test_ontology_rejects_unknown_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ontology").mkdir()
            (root / "ontology" / "payload.bin").write_text("x\n", encoding="utf-8")
            with self.assertRaises(CheckpointFailure) as caught:
                _scan_ontology(root)
            self.assertEqual(caught.exception.code, "BUILD_BROKEN:ONTOLOGY_SURFACE")

    def test_build_bootstrap_absence_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = _scan_build(Path(directory))
            self.assertEqual(observation["mode"], "bootstrap-absence")

    def test_build_rejects_orphan_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            with self.assertRaises(CheckpointFailure) as caught:
                _scan_build(root)
            self.assertEqual(caught.exception.code, "BUILD_BROKEN:ORPHAN_BUILD_SURFACE")

    def test_exact_head_checkpoint_replays_to_alive(self):
        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "GALL",
                "GIT_AUTHOR_EMAIL": "gall@example.invalid",
                "GIT_COMMITTER_NAME": "GALL",
                "GIT_COMMITTER_EMAIL": "gall@example.invalid",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
            (root / "README.md").write_text("# fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, env=env, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, env=env, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            context = Context(root=root, base="", head=head, repository="fixture/repo", changed_files=())
            receipt = execute_checkpoint("exact_head", context)
            self.assertEqual(receipt["standing"], "ALIVE")
            self.assertEqual(receipt["transitions"], ["CANDIDATE", "ADMITTED", "ALIVE"])
            self.assertTrue(receipt["negative_falsifier"]["passed"])
            self.assertTrue(receipt["replay"]["match"])


if __name__ == "__main__":
    unittest.main()
