from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ggen_create.model import GgenCreateError  # noqa: E402
from ggen_create.topology import (  # noqa: E402
    AdmittedRepositoryObservation,
    analyze_correspondence,
    decide_admission,
    observe_repository,
)


def _write_subject(root: Path) -> None:
    (root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (root / "ggen.toml").write_text("[project]\nname = \"x\"\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")


class TopologyTests(unittest.TestCase):
    def test_observe_repository_produces_bounded_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            self.assertIsInstance(observation, AdmittedRepositoryObservation)
            self.assertEqual(observation.schema, "ggen-create-topology-observation/1")
            self.assertEqual(observation.manifest["subject"]["file_count"], 3)
            self.assertEqual(observation.observed_at_digest, observation.manifest["subject"]["digest"])

    def test_correspondence_is_equal_when_subject_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            graph = analyze_correspondence(root, observation)
            self.assertTrue(graph.equal)
            self.assertEqual(graph.only_left, [])
            self.assertEqual(graph.only_right, [])
            self.assertEqual(graph.different, [])
            self.assertEqual(graph.checked_files, 3)

    def test_correspondence_detects_drift_on_tampered_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            (root / "src" / "main.py").write_text("print('tampered')\n", encoding="utf-8")
            graph = analyze_correspondence(root, observation)
            self.assertFalse(graph.equal)
            self.assertIn("src/main.py", graph.different)

    def test_correspondence_detects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            (root / "src" / "main.py").unlink()
            graph = analyze_correspondence(root, observation)
            self.assertFalse(graph.equal)
            self.assertIn("src/main.py", graph.only_left)

    def test_correspondence_refuses_missing_subject(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
        # root no longer exists once the tempdir context closes
        with self.assertRaises(GgenCreateError) as ctx:
            analyze_correspondence(root, observation)
        self.assertEqual(ctx.exception.code, "CORRESPONDENCE_SUBJECT_MISSING_REFUSED")

    def test_correspondence_refuses_malformed_observation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            with self.assertRaises(GgenCreateError) as ctx:
                analyze_correspondence(root, {"manifest": {"no_files_key": True}})
            self.assertEqual(ctx.exception.code, "TOPOLOGY_OBSERVATION_SCHEMA_MISMATCH_REFUSED")

    def test_admission_admits_when_no_blockers_and_no_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            (root / "RELEASE_CONTROL.md").write_text("rc\n", encoding="utf-8")
            (root / "ontology").mkdir()
            (root / "ontology" / "domain.ttl").write_text("# ontology\n", encoding="utf-8")
            (root / "schemas").mkdir()
            (root / "schemas" / "thing.schema.json").write_text("{}\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text("def test_x(): pass\n", encoding="utf-8")
            observation = observe_repository(root)
            graph = analyze_correspondence(root, observation)
            decision = decide_admission(observation, graph)
            self.assertEqual(decision.standing, "ADMITTED")
            self.assertEqual(decision.reasons, [])

    def test_admission_is_partial_alive_on_blockers_without_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            graph = analyze_correspondence(root, observation)
            decision = decide_admission(observation, graph)
            self.assertEqual(decision.standing, "PARTIAL_ALIVE")
            self.assertIn("blocker:release_control", decision.reasons)

    def test_admission_is_refused_on_drift_regardless_of_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            (root / "RELEASE_CONTROL.md").write_text("rc\n", encoding="utf-8")
            observation = observe_repository(root)
            (root / "src" / "main.py").write_text("print('tampered')\n", encoding="utf-8")
            graph = analyze_correspondence(root, observation)
            decision = decide_admission(observation, graph)
            self.assertEqual(decision.standing, "REFUSED")
            self.assertTrue(any(r.startswith("drift:different:") for r in decision.reasons))

    def test_admission_refuses_malformed_graph_or_observation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            graph = analyze_correspondence(root, observation)
            with self.assertRaises(GgenCreateError) as ctx:
                decide_admission(observation, {"no_equal_field": True})
            self.assertEqual(ctx.exception.code, "TOPOLOGY_CORRESPONDENCE_SCHEMA_MISMATCH_REFUSED")
            with self.assertRaises(GgenCreateError) as ctx:
                decide_admission({"no_manifest_field": True}, graph)
            self.assertEqual(ctx.exception.code, "TOPOLOGY_OBSERVATION_SCHEMA_MISMATCH_REFUSED")

    def test_dataclasses_serialize_to_plain_dicts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_subject(root)
            observation = observe_repository(root)
            graph = analyze_correspondence(root, observation)
            decision = decide_admission(observation, graph)
            json.dumps(observation.to_dict())
            json.dumps(graph.to_dict())
            json.dumps(decision.to_dict())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
