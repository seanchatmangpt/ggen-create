#!/usr/bin/env python3
"""Independently corroborate hygen-create parity against a live vendored submodule.

This is deliberately separate from `scripts/gall_hygen_parity.py`'s G0-G7 crown. That
crown proves internal consistency between hand-copied fixture files
(`examples/hygen-create-reference/*`) and their own hash manifest - it does not prove
those fixtures still match a live, working copy of upstream `hygen-create`.

This script does: it validates the vendored `vendor/hygen-create` git submodule (a) is
pinned to the exact commit ggen-create claims parity with, (b) actually builds and
passes its own test suite at that commit, (c) has example files that are still
byte-identical to the static fixtures, and (d) that ggen-create's own transform/
reconstruction logic reproduces that *live* tree byte-exactly - not just the static
copy.

Opt-in only: requires `git submodule update --init` plus Node/npm and network access to
install/build/test the upstream project, so it is intentionally NOT part of
`gall_hygen_parity.py`'s CHECKPOINTS tuple, the default GALL crown, or CI. Run it
manually:

    python3 scripts/gall_submodule_parity.py --root . --receipt submodule-parity-receipt.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gall_hygen_parity import (  # noqa: E402
    ALIVE,
    BUILD_BROKEN,
    REFERENCE_COMMIT,
    REFERENCE_REPOSITORY,
    UNSUPPORTED,
    GallFailure,
    _git_blob_sha,
    execute_example,
    manufacture,
)

SUBMODULE_RELATIVE = Path("vendor/hygen-create")
EXAMPLE_FILES = ("hygen-create.json", "package.json", "dist/hello.js", "test_strings.json")


def _submodule_root(root: Path) -> Path:
    return root / SUBMODULE_RELATIVE


def _run(command: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def check_submodule_pinned(root: Path) -> dict[str, Any]:
    submodule = _submodule_root(root)
    if not (submodule / "package.json").is_file():
        raise FileNotFoundError(
            "UNSUPPORTED:SUBMODULE_NOT_INITIALIZED:"
            "run `git submodule update --init vendor/hygen-create`"
        )
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("UNSUPPORTED:GIT_EXECUTABLE_MISSING")
    completed = _run([git, "rev-parse", "HEAD"], cwd=submodule, timeout=15)
    if completed.returncode != 0:
        raise GallFailure(f"BUILD_BROKEN:SUBMODULE_REV_PARSE_FAILED:{completed.stderr.strip()}")
    observed = completed.stdout.strip()
    if observed != REFERENCE_COMMIT:
        raise GallFailure(f"REFUSED:SUBMODULE_COMMIT_DRIFT:expected={REFERENCE_COMMIT}:observed={observed}")
    return {"repository": REFERENCE_REPOSITORY, "commit": observed}


def check_upstream_test_suite(root: Path) -> dict[str, Any]:
    submodule = _submodule_root(root)
    # Prefer yarn: the submodule ships yarn.lock pinning the exact dependency versions
    # in place when this commit's own tests last passed. `npm install` with no
    # package-lock.json re-resolves semver ranges against today's registry, which can
    # pull @types/* packages whose newer .d.ts syntax this project's old pinned
    # TypeScript compiler cannot parse - a toolchain-drift failure, not a real parity
    # break. yarn.lock avoids that by reproducing the original, validated dependency
    # graph.
    yarn = shutil.which("yarn")
    npm = shutil.which("npm")
    if yarn is not None and (submodule / "yarn.lock").is_file():
        # Not --frozen-lockfile: this 2018-era lockfile predates yarn 1.22's stricter
        # integrity checks and fails frozen validation even on an untouched checkout.
        # Plain `yarn install` still resolves from yarn.lock as its base and only
        # rewrites entries yarn's modern format requires - close enough to "the
        # dependency graph that was actually validated" for this corroboration check.
        install_command = [yarn, "install"]
        run_command = [yarn, "run"]
        test_command = [yarn, "test"]
    elif npm is not None:
        install_command = [npm, "install", "--no-audit", "--no-fund"]
        run_command = [npm, "run"]
        test_command = [npm, "test"]
    else:
        raise FileNotFoundError("UNSUPPORTED:NPM_EXECUTABLE_MISSING")
    # Run in a clean temporary copy, not in place: Yarn Classic's corepack-compat check
    # walks up the directory tree looking for the nearest package.json and can pick up
    # an unrelated ancestor project's "packageManager" field if one happens to exist
    # above this checkout on disk. A hermetic copy guarantees the install/build/test
    # boundary is exactly this submodule, regardless of where the parent repo happens
    # to be checked out.
    # Prefer the real filesystem /tmp over tempfile's default (which may honor a
    # sandboxed TMPDIR still nested under the user's home directory - exactly the
    # ancestry Yarn's walk-up needs to escape).
    hermetic_base = "/tmp" if Path("/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="ggen-create-submodule-upstream-", dir=hermetic_base) as raw:
        workdir = Path(raw) / "hygen-create"
        shutil.copytree(submodule, workdir, ignore=shutil.ignore_patterns(".git", "node_modules", "dist"))
        steps: dict[str, Any] = {}
        for label, command in (
            ("install", install_command),
            ("build", [*run_command, "build"]),
            ("test", test_command),
        ):
            started = time.monotonic()
            completed = _run(command, cwd=workdir, timeout=600)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            steps[label] = {
                "command": " ".join(command),
                "exit_code": completed.returncode,
                "elapsed_ms": elapsed_ms,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
            }
            if completed.returncode != 0:
                raise GallFailure(
                    f"BUILD_BROKEN:UPSTREAM_TEST_FAILED:{label}:"
                    + (completed.stderr.strip()[-2000:] or completed.stdout.strip()[-2000:])
                )
        return steps


def check_live_blob_match(root: Path) -> dict[str, Any]:
    submodule = _submodule_root(root)
    fixture_root = root / "examples" / "hygen-create-reference"
    manifest = json.loads((fixture_root / "parity.json").read_text(encoding="utf-8"))
    mismatched: list[str] = []
    checked: dict[str, str] = {}
    for relative in EXAMPLE_FILES:
        live_path = submodule / "example" / relative
        if not live_path.is_file():
            raise GallFailure(f"BUILD_BROKEN:LIVE_EXAMPLE_FILE_MISSING:{relative}")
        live_sha = _git_blob_sha(live_path.read_bytes())
        expected_sha = manifest["files"][relative]
        checked[relative] = live_sha
        if live_sha != expected_sha:
            mismatched.append(f"{relative}:expected={expected_sha}:live={live_sha}")
    if mismatched:
        raise GallFailure(f"BUILD_BROKEN:FIXTURE_DRIFT_FROM_LIVE_SUBMODULE:{mismatched!r}")
    return {"files": checked}


def check_live_reconstruction(root: Path) -> dict[str, Any]:
    submodule = _submodule_root(root)
    example_root = submodule / "example"
    with tempfile.TemporaryDirectory(prefix="ggen-create-submodule-hello-") as hello_raw:
        hello_output = Path(hello_raw)
        hello_result = manufacture(example_root, hello_output, "Hello")
        for relative in ("hygen-create.json", "package.json", "dist/hello.js"):
            if (hello_output / relative).read_bytes() != (example_root / relative).read_bytes():
                raise GallFailure(f"BUILD_BROKEN:LIVE_RECONSTRUCTION_DRIFT:{relative}")
    with tempfile.TemporaryDirectory(prefix="ggen-create-submodule-hola-") as hola_raw:
        hola_output = Path(hola_raw)
        hola_result = manufacture(example_root, hola_output, "Hola")
        hola_result["execution"] = execute_example(hola_output)
    return {"hello": hello_result, "hola": hola_result}


CHECKPOINTS: tuple[tuple[str, str, Callable[[Path], dict[str, Any]]], ...] = (
    ("SM0_SUBMODULE_PINNED", "confirm the submodule checkout matches the pinned reference commit", check_submodule_pinned),
    ("SM1_UPSTREAM_TEST_SUITE", "prove upstream hygen-create itself builds and passes its own tests", check_upstream_test_suite),
    ("SM2_LIVE_BLOB_MATCH", "prove static fixtures are still byte-identical to a fresh live checkout", check_live_blob_match),
    ("SM3_LIVE_RECONSTRUCTION", "prove ggen-create's transform logic reproduces the live tree byte-exactly", check_live_reconstruction),
)


def run_checkpoints(root: Path) -> dict[str, Any]:
    root = root.resolve()
    started = time.monotonic()
    results: dict[str, Any] = {}
    failures: list[str] = []
    for checkpoint_id, purpose, function in CHECKPOINTS:
        checkpoint_started = time.monotonic()
        try:
            evidence = function(root)
            state = ALIVE
            failure = None
        except FileNotFoundError as exc:
            evidence = {}
            state = UNSUPPORTED
            failure = str(exc)
            failures.append(f"{checkpoint_id}:{failure}")
        except Exception as exc:  # receipt every failed boundary
            evidence = {}
            state = BUILD_BROKEN
            failure = str(exc)
            failures.append(f"{checkpoint_id}:{failure}")
        results[checkpoint_id] = {
            "purpose": purpose,
            "standing": state,
            "elapsed_ms": round((time.monotonic() - checkpoint_started) * 1000),
            "failure": failure,
            "evidence": evidence,
        }
    standing = ALIVE if not failures else BUILD_BROKEN
    return {
        "schema": "ggen-create.gall.submodule-parity.receipt.v1",
        "subject": {
            "repository": "seanchatmangpt/ggen-create",
            "reference_repository": REFERENCE_REPOSITORY,
            "reference_commit": REFERENCE_COMMIT,
            "submodule_path": str(SUBMODULE_RELATIVE),
            "root": str(root),
        },
        "checkpoints": results,
        "failures": failures,
        "standing": standing,
        "claim_ceiling": "SUBMODULE_LIVE_CONSEQUENCE_ONLY",
        "note": (
            "Independent corroboration only. Does not promote HYGEN_CREATE_PARITY_ALIVE "
            "or any GALL-admitted standing; see scripts/gall_hygen_parity.py and "
            "docs/gall.md for the checkpoints that do."
        ),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "replay": {
            "command": (
                "python3 scripts/gall_submodule_parity.py --root . "
                "--receipt submodule-parity-receipt.json"
            )
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--receipt", default="")
    args = parser.parse_args(argv)
    receipt = run_checkpoints(Path(args.root))
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if receipt["standing"] == ALIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
