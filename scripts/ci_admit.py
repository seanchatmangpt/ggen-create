#!/usr/bin/env python3
"""Manufacture an exact-head ggen-create CI admission receipt."""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, Sequence

sys.dont_write_bytecode = True

from ci_router import LANES, RoutingRefusal, discover_changed_files, github_outputs, route_paths

TAIL_LIMIT = 4000
CI_PYTHON = (
    "scripts/ci_router.py",
    "scripts/ci_admit.py",
    "scripts/gall_contract.py",
    "scripts/gall_surfaces.py",
    "scripts/gall_checkpoint.py",
    "scripts/gall_hygen_parity.py",
    "tests/test_ci_router.py",
    "tests/test_ci_gall.py",
)


def _run(check_id: str, command: Sequence[str], cwd: Path) -> dict[str, Any]:
    start = time.monotonic()
    done = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    passed = done.returncode == 0
    return {
        "id": check_id,
        "command": list(command),
        "exit_code": done.returncode,
        "elapsed_ms": round((time.monotonic() - start) * 1000),
        "passed": passed,
        "typed_failure": None if passed else f"BUILD_BROKEN:{check_id.upper()}_FAILED",
        "stdout_tail": done.stdout[-TAIL_LIMIT:],
        "stderr_tail": done.stderr[-TAIL_LIMIT:],
    }


def _record(check_id: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {
        "id": check_id,
        "command": ["internal"],
        "exit_code": 0 if passed else 1,
        "elapsed_ms": 0,
        "passed": passed,
        "typed_failure": None if passed else f"BUILD_BROKEN:{check_id.upper()}_FAILED",
        "stdout_tail": detail[-TAIL_LIMIT:] if passed else "",
        "stderr_tail": "" if passed else detail[-TAIL_LIMIT:],
    }


def _parse_structured(path: Path) -> None:
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("NUL byte refused")
    text = data.decode("utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        json.loads(text)
    elif suffix == ".toml":
        tomllib.loads(text)
    elif suffix == ".py":
        ast.parse(text, filename=str(path))
    elif suffix in {".yml", ".yaml"}:
        if not shutil.which("ruby"):
            raise RuntimeError("UNSUPPORTED:YAML_PARSER_MISSING")
        done = subprocess.run(
            ["ruby", "-e", "require 'yaml'; YAML.parse_file(ARGV.fetch(0))", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if done.returncode:
            raise ValueError(done.stderr.strip() or "YAML parse failed")


def _structured(root: Path, changed: list[str]) -> dict[str, Any]:
    start = time.monotonic()
    failures: list[str] = []
    parsed: list[str] = []
    for rel in changed:
        path = root / rel
        if not path.is_file() or path.suffix.lower() not in {".json", ".toml", ".py", ".yml", ".yaml"}:
            continue
        try:
            _parse_structured(path)
            parsed.append(rel)
        except Exception as exc:
            failures.append(f"{rel}: {exc}")
    return {
        "id": "structured_parse",
        "command": ["internal", "structured-file-parser"],
        "exit_code": 0 if not failures else 1,
        "elapsed_ms": round((time.monotonic() - start) * 1000),
        "passed": not failures,
        "typed_failure": None if not failures else "BUILD_BROKEN:STRUCTURED_PARSE_FAILED",
        "stdout_tail": json.dumps({"parsed": parsed}, sort_keys=True),
        "stderr_tail": "\n".join(failures)[-TAIL_LIMIT:],
    }


def _shape(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    readme = root / "README.md"
    if not readme.is_file() or not readme.read_text(encoding="utf-8").startswith("# ggen-create"):
        failures.append("README.md must identify ggen-create")
    for required in ("docs", "ontology", "scripts", "tests", ".github/workflows", "src"):
        if not (root / required).is_dir():
            failures.append(f"missing required CI-owned surface: {required}")
    for required_file in (
        *CI_PYTHON,
        "docs/ci.md",
        "docs/gall.md",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "src/ggen_create/__init__.py",
    ):
        if not (root / required_file).is_file():
            failures.append(f"missing required evidence file: {required_file}")
    return _record("repository_shape", not failures, "; ".join(failures) or "required surfaces present")


def _lane(root: Path, lane: str) -> int:
    checks: list[dict[str, Any]] = []
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if lane == "ci":
        checks += [
            _run("ci_unit", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_ci_*.py"], root),
            _run("ci_compile", [sys.executable, "-m", "py_compile", *CI_PYTHON], root),
            _structured(root, [".github/workflows/ci.yml"]),
            _run(
                "gall_ci_checkpoint",
                [sys.executable, "scripts/gall_checkpoint.py", "--checkpoint", "ci", "--head", head, "--receipt", os.devnull],
                root,
            ),
        ]
    elif lane == "docs":
        checks.append(
            _run(
                "gall_docs_checkpoint",
                [sys.executable, "scripts/gall_checkpoint.py", "--checkpoint", "docs", "--head", head, "--receipt", os.devnull],
                root,
            )
        )
        parity = root / "scripts/gall_hygen_parity.py"
        if parity.is_file():
            checks.append(
                _run(
                    "hygen_docs_gall",
                    [sys.executable, str(parity.relative_to(root)), "--root", ".", "--receipt", "gall-hygen-parity-receipt.json"],
                    root,
                )
            )
    elif lane == "ontology":
        checks.append(
            _run(
                "gall_ontology_checkpoint",
                [sys.executable, "scripts/gall_checkpoint.py", "--checkpoint", "ontology", "--head", head, "--receipt", os.devnull],
                root,
            )
        )
    elif lane == "build":
        checks.append(
            _run(
                "gall_build_checkpoint",
                [sys.executable, "scripts/gall_checkpoint.py", "--checkpoint", "build", "--head", head, "--receipt", os.devnull],
                root,
            )
        )
        if (root / "pyproject.toml").is_file():
            checks += [
                _run(
                    "product_install",
                    [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
                    root,
                ),
                _run(
                    "product_unit",
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                    root,
                ),
            ]
        parity = root / "scripts/gall_hygen_parity.py"
        if parity.is_file():
            checks += [
                _run(
                    "hygen_parity_unit",
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_parity_*.py", "-v"],
                    root,
                ),
                _run(
                    "hygen_parity_gall",
                    [sys.executable, str(parity.relative_to(root)), "--root", ".", "--receipt", "gall-hygen-parity-receipt.json"],
                    root,
                ),
            ]
    print(json.dumps({"lane": lane, "checks": checks}, indent=2, sort_keys=True))
    return 0 if all(check["passed"] for check in checks) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--receipt", default="ci-errc-receipt.json")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--lane", choices=("build", "ci", "docs", "ontology"))
    args = parser.parse_args(argv)
    root = Path.cwd()
    if args.lane:
        return _lane(root, args.lane)

    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    changed: list[str] = []
    routing = {"fast_only": [], **{lane: [] for lane in LANES}}
    outputs = github_outputs(routing)
    try:
        observed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        actual = observed.stdout.strip()
        exact = observed.returncode == 0 and bool(args.head) and actual == args.head
        checks.append(_record("exact_head_identity", exact, f"expected={args.head} observed={actual}"))
        if not exact:
            failures.append("REFUSED:HEAD_IDENTITY_MISMATCH")
        changed = sorted(set(args.changed_file or discover_changed_files(args.base, args.head, str(root))))
        routing = route_paths(changed)
        outputs = github_outputs(routing)
        checks.append(_record("changed_file_routing", True, json.dumps(routing, sort_keys=True)))
        checks += [
            _run("router_self_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_ci_*.py"], root),
            _run("python_compile", [sys.executable, "-m", "py_compile", *CI_PYTHON], root),
            _structured(root, changed),
            _shape(root),
        ]
    except RoutingRefusal as refusal:
        failures.append(refusal.reason)
        checks.append(_record("changed_file_routing", False, refusal.detail))
    except Exception as exc:
        failures.append("BUILD_BROKEN:FAST_GATE_INTERNAL_ERROR")
        checks.append(_record("fast_gate_internal", False, repr(exc)))

    failures += [check["typed_failure"] for check in checks if check["typed_failure"]]
    standing = "ALIVE" if not failures else "BUILD_BROKEN"
    receipt = {
        "schema": "ggen-create.ci.errc.receipt.v2",
        "subject": {
            "repository": args.repository,
            "base": args.base,
            "head": args.head,
            "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
            "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        },
        "errc": {
            "eliminate": ["unowned all-PR fan-out", "mutable action references", "ambiguous skipped-check standing"],
            "reduce": ["deep lane frequency", "time-to-first-falsifier"],
            "raise": ["exact-head identity", "deterministic routing", "failure transparency", "replay authority"],
            "create": ["universal fast gate", "path-owned lanes", "GALL crown", "machine-readable receipt"],
        },
        "changed_files": changed,
        "routing": routing,
        "checks": checks,
        "failures": sorted(set(failures)),
        "standing": standing,
        "claim_ceiling": "EXACT_HEAD_FAST_AUTHORITY_AND_ROUTING_ONLY",
        "replay": {
            "command": [
                "python3",
                "scripts/ci_admit.py",
                "--base",
                args.base,
                "--head",
                args.head,
                "--repository",
                args.repository,
                "--receipt",
                args.receipt,
            ]
        },
    }
    Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if standing == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
