#!/usr/bin/env python3
"""Core GALL admission and receipt contract."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

SCHEMA = "ggen-create.gall.checkpoint.v1"
CROWN_SCHEMA = "ggen-create.gall.crown.v1"
SEED = 0
CHECKPOINTS = (
    "exact_head",
    "clean_tree",
    "routing",
    "ci",
    "docs",
    "ontology",
    "build",
    "receipt",
)
OWNERS = dict(zip(CHECKPOINTS, (
    "release-law", "release-law", "ci-router", "ci-self",
    "documentation", "ontology", "build", "evidence",
)))
CEILINGS = {
    "exact_head": "EXACT_REVISION_IDENTITY_ONLY",
    "clean_tree": "CLEAN_WORKTREE_ONLY",
    "routing": "DETERMINISTIC_PATH_OWNERSHIP_ONLY",
    "ci": "CI_IMPLEMENTATION_AND_WORKFLOW_SYNTAX_ONLY",
    "docs": "DOCUMENT_INTEGRITY_ONLY",
    "ontology": "ONTOLOGY_SURFACE_INTEGRITY_ONLY",
    "build": "ADMITTED_BUILD_SURFACE_ONLY",
    "receipt": "GALL_RECEIPT_CONTRACT_ONLY",
}


class CheckpointFailure(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Context:
    root: Path
    base: str
    head: str
    repository: str
    changed_files: tuple[str, ...]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env or {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def require(command: list[str], cwd: Path, code: str) -> subprocess.CompletedProcess[str]:
    completed = run(command, cwd)
    if completed.returncode:
        detail = completed.stderr or completed.stdout or repr(command)
        raise CheckpointFailure(code, detail[-4000:])
    return completed


def verify_exact_head(root: Path, expected: str) -> dict[str, Any]:
    observed = require(
        ["git", "rev-parse", "HEAD"], root, "REFUSED:HEAD_UNOBSERVABLE"
    ).stdout.strip()
    if not expected or observed != expected:
        raise CheckpointFailure(
            "REFUSED:HEAD_IDENTITY_MISMATCH",
            f"expected={expected} observed={observed}",
        )
    return {"expected": expected, "observed": observed}


def verify_clean_tree(root: Path) -> dict[str, Any]:
    lines = require(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        root,
        "REFUSED:WORKTREE_UNOBSERVABLE",
    ).stdout.splitlines()
    dirty = [line for line in lines if line.strip()]
    if dirty:
        raise CheckpointFailure("REFUSED:DIRTY_WORKTREE", "\n".join(dirty))
    return {"clean": True, "dirty_entries": []}


def sample_receipt(head: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "checkpoint": "sample",
        "subject": {"revision": head},
        "transitions": ["CANDIDATE", "ADMITTED", "ALIVE"],
        "positive_witness": {"passed": True, "observation_sha256": "0" * 64},
        "negative_falsifier": {
            "passed": True,
            "expected_failure": "REFUSED:SAMPLE",
            "observed_failure": "REFUSED:SAMPLE",
        },
        "replay": {"passed": True, "match": True},
        "standing": "ALIVE",
    }


def validate_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "checkpoint", "subject", "transitions", "positive_witness",
        "negative_falsifier", "replay", "standing",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise CheckpointFailure("BUILD_BROKEN:RECEIPT_FIELDS_MISSING", ",".join(missing))
    if payload["schema"] != SCHEMA:
        raise CheckpointFailure("BUILD_BROKEN:RECEIPT_SCHEMA", str(payload["schema"]))
    transition = payload["transitions"]
    if transition != ["CANDIDATE", "ADMITTED", "ALIVE"]:
        raise CheckpointFailure("BUILD_BROKEN:ILLEGAL_STANDING_TRANSITION", repr(transition))
    if payload["standing"] != "ALIVE" or not payload["positive_witness"].get("passed"):
        raise CheckpointFailure("BUILD_BROKEN:POSITIVE_WITNESS_MISSING", "not ALIVE")
    negative = payload["negative_falsifier"]
    if not negative.get("passed") or negative.get("expected_failure") != negative.get("observed_failure"):
        raise CheckpointFailure("BUILD_BROKEN:NEGATIVE_FALSIFIER_MISSING", repr(negative))
    replay = payload["replay"]
    if not replay.get("passed") or not replay.get("match"):
        raise CheckpointFailure("BUILD_BROKEN:REPLAY_MISSING", repr(replay))
    return {"required_fields": sorted(required), "transition": transition}
