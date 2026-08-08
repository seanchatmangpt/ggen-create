"""Phase 5 minimal agent topology: receiver -> correspondence-analyst -> admission-referee.

Real typed artifacts and real decision logic behind the three agents already registered
in `agents.py`. See `docs/superpowers/specs/2026-08-07-phase-5-agent-topology-design.md`
for the full design.

    receiver               -> topology.observe        -> AdmittedRepositoryObservation
    correspondence-analyst -> correspondence.analyze   -> CandidateCorrespondenceGraph
    admission-referee      -> admission.decide         -> AdmissionDecision

`AdmittedRepositoryObservation` wraps `legacy_model.plan_legacy_factory()`'s bounded
manifest of an arbitrary repository - reused directly as a function call, not via the
existing `legacy.plan` skill (that skill's own dispatch is scoped to ggen-legacy's
receiving-bundle flow, not this topology).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .legacy_model import plan_legacy_factory
from .model import GgenCreateError
from .runtime import digest_file, require_under

OBSERVATION_SCHEMA = "ggen-create-topology-observation/1"
CORRESPONDENCE_SCHEMA = "ggen-create-topology-correspondence/1"
ADMISSION_SCHEMA = "ggen-create-topology-admission/1"


@dataclass
class AdmittedRepositoryObservation:
    schema: str
    manifest: dict[str, Any]
    observed_at_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateCorrespondenceGraph:
    schema: str
    equal: bool
    only_left: list[str] = field(default_factory=list)
    only_right: list[str] = field(default_factory=list)
    different: list[str] = field(default_factory=list)
    checked_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdmissionDecision:
    schema: str
    standing: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe_repository(subject_root: Path, **factory_kwargs: Any) -> AdmittedRepositoryObservation:
    """receiver: bind a bounded, digest-backed manifest of an arbitrary repository."""
    manifest = plan_legacy_factory(subject_root, **factory_kwargs)
    return AdmittedRepositoryObservation(
        schema=OBSERVATION_SCHEMA,
        manifest=manifest,
        observed_at_digest=manifest["subject"]["digest"],
    )


def analyze_correspondence(
    subject_root: Path,
    observation: AdmittedRepositoryObservation | dict[str, Any],
) -> CandidateCorrespondenceGraph:
    """correspondence-analyst: re-walk the subject and diff recomputed digests against
    the recorded observation - proves the observation still corresponds to reality."""
    if isinstance(observation, AdmittedRepositoryObservation):
        manifest = observation.manifest
    elif isinstance(observation, dict):
        manifest = observation.get("manifest")
    else:
        manifest = None
    if not isinstance(manifest, dict) or "files" not in manifest:
        raise GgenCreateError(
            "TOPOLOGY_OBSERVATION_SCHEMA_MISMATCH_REFUSED",
            "observation is missing a manifest with a 'files' list",
        )
    root = subject_root.resolve()
    if not root.is_dir():
        raise GgenCreateError("CORRESPONDENCE_SUBJECT_MISSING_REFUSED", str(root))

    recorded: dict[str, str] = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    live: dict[str, str] = {}
    for entry in manifest["files"]:
        candidate = require_under(root, root / entry["path"], code="CORRESPONDENCE_PATH_ESCAPE_REFUSED")
        if candidate.is_file():
            live[entry["path"]] = digest_file(candidate)

    recorded_paths = set(recorded)
    live_paths = set(live)
    only_left = sorted(recorded_paths - live_paths)
    only_right = sorted(live_paths - recorded_paths)
    different = sorted(
        path
        for path in recorded_paths & live_paths
        if recorded[path] != live[path]
    )
    equal = not only_left and not only_right and not different
    return CandidateCorrespondenceGraph(
        schema=CORRESPONDENCE_SCHEMA,
        equal=equal,
        only_left=only_left,
        only_right=only_right,
        different=different,
        checked_files=len(recorded_paths | live_paths),
    )


def decide_admission(
    observation: AdmittedRepositoryObservation | dict[str, Any],
    graph: CandidateCorrespondenceGraph | dict[str, Any],
) -> AdmissionDecision:
    """admission-referee: CANDIDATE -> ADMITTED / PARTIAL_ALIVE / REFUSED.

    Drift (the correspondence graph is not equal) is a hard REFUSED gate - the observed
    manifest no longer corresponds to the subject on disk. Absent drift, declared
    blockers on the manifest (missing AGENTS.md/RELEASE_CONTROL.md/ggen.toml, etc.)
    downgrade the standing to PARTIAL_ALIVE rather than a full ADMITTED.
    """
    if isinstance(graph, CandidateCorrespondenceGraph):
        graph_equal, graph_different = graph.equal, graph.different
        graph_only_left, graph_only_right = graph.only_left, graph.only_right
    elif isinstance(graph, dict) and "equal" in graph:
        graph_equal = graph["equal"]
        graph_different = graph.get("different", [])
        graph_only_left = graph.get("only_left", [])
        graph_only_right = graph.get("only_right", [])
    else:
        raise GgenCreateError(
            "TOPOLOGY_CORRESPONDENCE_SCHEMA_MISMATCH_REFUSED",
            "graph is missing an 'equal' field",
        )

    if isinstance(observation, AdmittedRepositoryObservation):
        manifest = observation.manifest
    elif isinstance(observation, dict) and isinstance(observation.get("manifest"), dict):
        manifest = observation["manifest"]
    else:
        raise GgenCreateError(
            "TOPOLOGY_OBSERVATION_SCHEMA_MISMATCH_REFUSED",
            "observation is missing a manifest",
        )
    blockers = list(manifest.get("blockers", []))

    if not graph_equal:
        reasons = [f"drift:different:{p}" for p in graph_different]
        reasons += [f"drift:only_left:{p}" for p in graph_only_left]
        reasons += [f"drift:only_right:{p}" for p in graph_only_right]
        return AdmissionDecision(schema=ADMISSION_SCHEMA, standing="REFUSED", reasons=reasons)
    if blockers:
        return AdmissionDecision(
            schema=ADMISSION_SCHEMA,
            standing="PARTIAL_ALIVE",
            reasons=[f"blocker:{b}" for b in blockers],
        )
    return AdmissionDecision(schema=ADMISSION_SCHEMA, standing="ADMITTED", reasons=[])
