#!/usr/bin/env python3
"""Promote exact-head GALL checkpoints from CANDIDATE to ALIVE."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from ci_router import LANES, RoutingRefusal, discover_changed_files, github_outputs, route_paths
from gall_contract import (
    CEILINGS, CHECKPOINTS, CROWN_SCHEMA, OWNERS, SCHEMA, SEED,
    CheckpointFailure, Context, canonical, digest, require,
    sample_receipt as _sample_receipt,
    validate_receipt as _validate_receipt,
    verify_clean_tree, verify_exact_head,
)
from gall_surfaces import (
    negative_build, negative_ci, negative_clean, negative_docs, negative_exact,
    negative_ontology, negative_receipt, negative_routing,
    scan_build as _scan_build,
    scan_docs as _scan_docs,
    scan_ontology as _scan_ontology,
)


def changed(context: Context) -> list[str]:
    if context.changed_files:
        return sorted(set(context.changed_files))
    return discover_changed_files(context.base, context.head, str(context.root))


def probe_exact(context: Context) -> dict[str, Any]:
    return verify_exact_head(context.root, context.head)


def probe_clean(context: Context) -> dict[str, Any]:
    return verify_clean_tree(context.root)


def probe_routing(context: Context) -> dict[str, Any]:
    files = changed(context)
    report = route_paths(files)
    if sorted(report) != sorted(("fast_only", *LANES)):
        raise CheckpointFailure("BUILD_BROKEN:ROUTING_SHAPE", repr(sorted(report)))
    return {"changed_files": files, "routing": report, "outputs": github_outputs(report)}


def probe_ci(context: Context) -> dict[str, Any]:
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_ci_*.py"],
        [
            sys.executable, "-m", "py_compile",
            "scripts/ci_router.py", "scripts/ci_admit.py", "scripts/gall_contract.py",
            "scripts/gall_surfaces.py", "scripts/gall_checkpoint.py",
            "tests/test_ci_router.py", "tests/test_ci_gall.py",
        ],
        ["ruby", "-e", "require 'yaml'; YAML.parse_file(ARGV.fetch(0))", ".github/workflows/ci.yml"],
    ]
    if not shutil.which("ruby"):
        raise CheckpointFailure("UNSUPPORTED:YAML_PARSER_MISSING", "ruby required")
    for index, command in enumerate(commands):
        require(command, context.root, f"BUILD_BROKEN:CI_COMMAND_{index}_FAILED")
    return {"commands": commands, "test_pattern": "test_ci_*.py"}


def probe_docs(context: Context) -> dict[str, Any]:
    return _scan_docs(context.root)


def probe_ontology(context: Context) -> dict[str, Any]:
    return _scan_ontology(context.root)


def probe_build(context: Context) -> dict[str, Any]:
    return _scan_build(context.root)


def probe_receipt(context: Context) -> dict[str, Any]:
    return _validate_receipt(_sample_receipt(context.head))


PROBES = {
    "exact_head": probe_exact,
    "clean_tree": probe_clean,
    "routing": probe_routing,
    "ci": probe_ci,
    "docs": probe_docs,
    "ontology": probe_ontology,
    "build": probe_build,
    "receipt": probe_receipt,
}
NEGATIVES = {
    "exact_head": negative_exact,
    "clean_tree": negative_clean,
    "routing": negative_routing,
    "ci": negative_ci,
    "docs": negative_docs,
    "ontology": negative_ontology,
    "build": negative_build,
    "receipt": negative_receipt,
}


def replay(name: str, context: Context, positive: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable, str(Path(__file__).resolve()), "--probe", name,
        "--base", context.base, "--head", context.head,
        "--repository", context.repository,
    ]
    for path in context.changed_files:
        command += ["--changed-file", path]
    replayed = json.loads(require(
        command, context.root, "BUILD_BROKEN:REPLAY_PROCESS_FAILED"
    ).stdout)
    expected, observed = digest(positive), digest(replayed)
    if expected != observed:
        raise CheckpointFailure(
            "BUILD_BROKEN:NONDETERMINISTIC_REPLAY",
            f"expected={expected} observed={observed}",
        )
    return {
        "passed": True,
        "match": True,
        "process": "subprocess",
        "command": command,
        "observation_sha256": observed,
    }


def execute_checkpoint(name: str, context: Context) -> dict[str, Any]:
    transitions = ["CANDIDATE"]
    try:
        identity = verify_exact_head(context.root, context.head)
        clean = verify_clean_tree(context.root)
        transitions.append("ADMITTED")
        positive = PROBES[name](context)
        negative = NEGATIVES[name](context)
        replay_receipt = replay(name, context, positive)
        transitions.append("ALIVE")
        receipt = {
            "schema": SCHEMA,
            "checkpoint": name,
            "owner": OWNERS[name],
            "subject": {
                "repository": context.repository,
                "base": context.base,
                "revision": context.head,
                "clean": True,
            },
            "deterministic_seed": SEED,
            "transitions": transitions,
            "admission": {"exact_head": identity, "clean_tree": clean},
            "positive_witness": {
                "passed": True,
                "observation": positive,
                "observation_sha256": digest(positive),
            },
            "negative_falsifier": negative,
            "replay": replay_receipt,
            "standing": "ALIVE",
            "claim_ceiling": CEILINGS[name],
        }
        _validate_receipt(receipt)
        return receipt
    except (CheckpointFailure, RoutingRefusal, KeyError) as error:
        if isinstance(error, CheckpointFailure):
            code, detail = error.code, error.detail
        elif isinstance(error, RoutingRefusal):
            code, detail = error.reason, error.detail
        else:
            code, detail = "REFUSED:UNKNOWN_CHECKPOINT", str(error)
        return {
            "schema": SCHEMA,
            "checkpoint": name,
            "owner": OWNERS.get(name, "unknown"),
            "subject": {"repository": context.repository, "base": context.base, "revision": context.head},
            "deterministic_seed": SEED,
            "transitions": [*transitions, "REFUSED"],
            "failure": {"code": code, "detail": detail},
            "standing": code,
            "claim_ceiling": "NO_CLAIM",
        }


def execute_crown(context: Context) -> dict[str, Any]:
    receipts = [execute_checkpoint(name, context) for name in CHECKPOINTS]
    failures = [receipt for receipt in receipts if receipt["standing"] != "ALIVE"]
    return {
        "schema": CROWN_SCHEMA,
        "subject": {"repository": context.repository, "base": context.base, "revision": context.head},
        "deterministic_seed": SEED,
        "checkpoints": receipts,
        "checkpoint_standings": {receipt["checkpoint"]: receipt["standing"] for receipt in receipts},
        "failures": [receipt.get("failure", {"code": receipt["standing"]}) for receipt in failures],
        "standing": "ALIVE" if not failures else "PARTIAL_ALIVE",
        "claim_ceiling": "EXACT_HEAD_CLEAN_REPLAYED_CHECKPOINTS_ONLY" if not failures else "NO_CROWN_CLAIM",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--checkpoint", choices=(*CHECKPOINTS, "all"))
    group.add_argument("--probe", choices=CHECKPOINTS)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--receipt", default="")
    args = parser.parse_args(argv)
    context = Context(
        Path.cwd().resolve(), args.base, args.head, args.repository,
        tuple(sorted(set(args.changed_file))),
    )
    if args.probe:
        try:
            print(canonical(PROBES[args.probe](context)))
            return 0
        except (CheckpointFailure, RoutingRefusal) as error:
            code = error.code if isinstance(error, CheckpointFailure) else error.reason
            print(json.dumps({"standing": code, "detail": error.detail}, sort_keys=True), file=sys.stderr)
            return 2
    payload = execute_crown(context) if args.checkpoint == "all" else execute_checkpoint(args.checkpoint, context)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["standing"] == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
