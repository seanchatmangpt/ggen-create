#!/usr/bin/env python3
"""Deterministic changed-file router for ggen-create CI evidence lanes."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

LANES = ("build_deep", "ci_deep", "docs_deep", "ontology_deep")


class RoutingRefusal(RuntimeError):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _normalize(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    pure = PurePosixPath(candidate)
    if not candidate or pure.is_absolute() or ".." in pure.parts:
        raise RoutingRefusal("REFUSED:INVALID_CHANGED_PATH", repr(path))
    normalized = pure.as_posix()
    if normalized == ".":
        raise RoutingRefusal("REFUSED:INVALID_CHANGED_PATH", repr(path))
    return normalized


def _is_ci(path: str) -> bool:
    return (
        path.startswith(".github/")
        or path in {
            "scripts/ci_router.py",
            "scripts/ci_admit.py",
            "scripts/gall_contract.py",
            "scripts/gall_surfaces.py",
            "scripts/gall_checkpoint.py",
            "docs/ci.md",
            "docs/gall.md",
        }
        or path.startswith("tests/test_ci_")
    )


def _is_docs(path: str) -> bool:
    return path in {"README.md", "BOOTSTRAP.md"} or path.startswith("docs/") or path.endswith(".md")


def _is_ontology(path: str) -> bool:
    return path.startswith("ontology/")


def _is_build(path: str) -> bool:
    if path in {"Cargo.toml", "Cargo.lock", "build.rs", "rust-toolchain", "rust-toolchain.toml", "deny.toml"}:
        return True
    if path.startswith(("src/", "crates/", "examples/", "benches/", "fixtures/")):
        return True
    return path.startswith("tests/") and not path.startswith("tests/test_ci_")


def route_paths(paths: Iterable[str]) -> dict[str, list[str]]:
    normalized = sorted({_normalize(path) for path in paths})
    routed = {"fast_only": [], **{lane: [] for lane in LANES}}
    for path in normalized:
        matched = False
        if _is_ci(path):
            routed["ci_deep"].append(path)
            matched = True
        if _is_docs(path):
            routed["docs_deep"].append(path)
            matched = True
        if _is_ontology(path):
            routed["ontology_deep"].append(path)
            matched = True
        if _is_build(path):
            routed["build_deep"].append(path)
            matched = True
        if not matched:
            routed["fast_only" if path in {".gitignore", "LICENSE"} else "build_deep"].append(path)
    return routed


def discover_changed_files(base: str, head: str, cwd: str = ".") -> list[str]:
    if not head:
        raise RoutingRefusal("REFUSED:MISSING_HEAD_IDENTITY", "head SHA is empty")
    if not base or set(base) == {"0"}:
        parent = subprocess.run(
            ["git", "rev-parse", f"{head}^"],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        base = parent.stdout.strip() if parent.returncode == 0 else ""
    command = (
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base, head, "--"]
        if base
        else ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", head]
    )
    done = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode:
        raise RoutingRefusal(
            "REFUSED:CHANGED_FILE_DISCOVERY_FAILED",
            done.stderr.strip() or done.stdout.strip() or "git changed-file discovery failed",
        )
    return sorted({_normalize(line) for line in done.stdout.splitlines() if line.strip()})


def github_outputs(report: Mapping[str, list[str]]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for lane in LANES:
        outputs[lane] = "true" if report[lane] else "false"
        outputs[f"{lane}_files"] = json.dumps(report[lane], separators=(",", ":"))
    outputs["routing_json"] = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--report", default="")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args(argv)
    try:
        changed = args.changed_file or discover_changed_files(args.base, args.head)
        report = route_paths(changed)
        outputs = github_outputs(report)
        payload = {
            "schema": "ggen-create.ci.routing.v1",
            "base": args.base,
            "head": args.head,
            "changed_files": sorted({_normalize(p) for p in changed}),
            "routing": report,
            "outputs": outputs,
            "standing": "ALIVE",
        }
    except RoutingRefusal as refusal:
        payload = {
            "schema": "ggen-create.ci.routing.v1",
            "base": args.base,
            "head": args.head,
            "changed_files": [],
            "routing": {"fast_only": [], **{lane: [] for lane in LANES}},
            "outputs": {lane: "false" for lane in LANES},
            "standing": refusal.reason,
            "failure": refusal.detail,
        }
        if args.report:
            Path(args.report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 2
    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
