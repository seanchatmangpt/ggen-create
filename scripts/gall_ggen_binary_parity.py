#!/usr/bin/env python3
"""Prove ggen-create's P0-P6 pipeline actually works against a real `ggen` binary.

Every existing parity checkpoint (G0-G7 in `gall_hygen_parity.py`, SM0-SM3 in
`gall_submodule_parity.py`) either compares static fixtures against a manifest, or
reconstructs trees with ggen-create's own Python transform logic. None of them have ever
invoked a real `ggen` binary - `src/ggen_create/verify.py`'s P0-P7 pipeline has real-binary
support (`_run_ggen` shells out to `ggen_bin`), but nothing in the repo has exercised it,
and README/ROADMAP/PRD all mark `real public ggen parity crown (P7)` as `UNKNOWN`.

This script closes that specific, narrow gap: it builds a real ggen-create session from
the live `vendor/hygen-create` submodule, then calls `verify_parity` with a real `ggen`
binary. It deliberately stops short of the full P7 crown - that additionally requires a
`reference_dir` produced by the real upstream `hygen` render step (a separate npm package
from `hygen-create`, which only captures/templatizes), which this script does not attempt.
See `ROADMAP.md`'s "80/20 ERRC" section for why that's scoped as a distinct follow-on.

Opt-in only: requires a real `ggen` binary on PATH (or $GGEN_BIN) and the
`vendor/hygen-create` submodule initialized. Not part of `gall_hygen_parity.py`'s
CHECKPOINTS tuple, the default GALL crown, or CI. Run it manually:

    python3 scripts/gall_ggen_binary_parity.py --root . --receipt ggen-binary-parity-receipt.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gall_hygen_parity import ALIVE, BUILD_BROKEN, UNSUPPORTED, GallFailure  # noqa: E402
from ggen_create.session import add_paths, set_seed, start_session  # noqa: E402
from ggen_create.verify import verify_parity  # noqa: E402

SUBMODULE_EXAMPLE = Path("vendor/hygen-create/example")


def check_ggen_binary_available(root: Path) -> dict[str, Any]:
    ggen_bin = os.environ.get("GGEN_BIN", "ggen")
    resolved = shutil.which(ggen_bin)
    if resolved is None:
        raise FileNotFoundError(f"UNSUPPORTED:GGEN_EXECUTABLE_MISSING:{ggen_bin}")
    completed = subprocess.run(
        [resolved, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        raise GallFailure(f"BUILD_BROKEN:GGEN_VERSION_CHECK_FAILED:{completed.stderr.strip()}")
    return {"ggen_bin": resolved, "version_output": (completed.stdout + completed.stderr).strip()}


def _materialize_session(example_root: Path, session_root: Path) -> Path:
    # add_paths enforces that captured files live under the session's own capture root
    # (path-containment law) - so the live submodule's files are copied into the session
    # root first, rather than added in place from vendor/hygen-create/example/, which
    # would also leave a stray ggen-create.json inside the tracked submodule checkout.
    for relative in ("package.json", "dist/hello.js"):
        source = example_root / relative
        destination = session_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    session_path = start_session(session_root, "greeter")
    add_paths(session_path, ["package.json", "dist/hello.js"], cwd=session_root)
    set_seed(session_path, "Hello")
    return session_path


def check_session_from_live_submodule(root: Path) -> dict[str, Any]:
    example_root = root / SUBMODULE_EXAMPLE
    if not (example_root / "package.json").is_file():
        raise FileNotFoundError(
            "UNSUPPORTED:SUBMODULE_NOT_INITIALIZED:"
            "run `git submodule update --init vendor/hygen-create`"
        )
    with tempfile.TemporaryDirectory(prefix="ggen-create-ggenbin-session-") as raw:
        session_root = Path(raw)
        session_path = _materialize_session(example_root, session_root)
        session = json.loads(session_path.read_text(encoding="utf-8"))
        return {"session_root": str(session_root), "added_files": sorted(session["files_and_dirs"])}


def check_real_ggen_sync_run(root: Path) -> dict[str, Any]:
    ggen_bin = check_ggen_binary_available(root)["ggen_bin"]
    example_root = root / SUBMODULE_EXAMPLE
    with tempfile.TemporaryDirectory(prefix="ggen-create-ggenbin-verify-") as raw:
        session_root = Path(raw) / "session"
        session_root.mkdir()
        session_path = _materialize_session(example_root, session_root)
        report = verify_parity(
            session_path,
            output_root=Path(raw) / "verify",
            ggen_bin=ggen_bin,
            variation_value="Hola",
            sync_args=["sync", "run"],
        )
        if report["checkpoints"]["P6_REVISION_PARITY"] != ALIVE:
            raise GallFailure(
                f"BUILD_BROKEN:P6_REVISION_PARITY_NOT_ALIVE:{report['checkpoints']!r}"
            )
        if report["checkpoints"]["P7_PARITY_CROWN"] != "PARTIAL_ALIVE":
            # Expected: no reference_dir/reference_id supplied, so P7 should stay
            # PARTIAL_ALIVE (correctly refusing to claim the full crown), not ALIVE or
            # REFUSED. Anything else means verify_parity's crown gating changed
            # underneath this checkpoint.
            raise GallFailure(
                f"BUILD_BROKEN:P7_UNEXPECTED_STANDING:{report['checkpoints']['P7_PARITY_CROWN']!r}"
            )
        # Confirm the report was actually written to disk while its temp directory is
        # still alive - the caller's tempdir is cleaned up on return, so this is the
        # only point at which an on-disk check is possible.
        report_path = Path(report["report_path"])
        if not report_path.is_file():
            raise GallFailure(f"BUILD_BROKEN:REPORT_NOT_WRITTEN:{report_path}")
        on_disk = json.loads(report_path.read_text(encoding="utf-8"))
        return {
            "checkpoints": report["checkpoints"],
            "report_path_existed_on_disk": True,
            "ggen": on_disk["ggen"],
        }


def check_report_shape(root: Path) -> dict[str, Any]:
    evidence = check_real_ggen_sync_run(root)
    ggen = evidence["ggen"]
    if ggen["sync_args"] != ["sync", "run"]:
        raise GallFailure(f"BUILD_BROKEN:REPORT_SYNC_ARGS_DRIFT:{ggen!r}")
    if not ggen["binary"]:
        raise GallFailure("BUILD_BROKEN:REPORT_BINARY_FIELD_EMPTY")
    return {"ggen": ggen}


CHECKPOINTS: tuple[tuple[str, str, Callable[[Path], dict[str, Any]]], ...] = (
    ("GB0_GGEN_BINARY_AVAILABLE", "confirm a real ggen binary resolves and reports a version", check_ggen_binary_available),
    ("GB1_SESSION_FROM_LIVE_SUBMODULE", "capture a ggen-create session from the live submodule example", check_session_from_live_submodule),
    ("GB2_REAL_GGEN_SYNC_RUN", "run verify_parity end-to-end against the real ggen binary (P0-P6)", check_real_ggen_sync_run),
    ("GB3_REPORT_SHAPE", "confirm parity-report.json reflects the real subprocess invocation", check_report_shape),
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
        "schema": "ggen-create.gall.ggen-binary-parity.receipt.v1",
        "subject": {
            "repository": "seanchatmangpt/ggen-create",
            "submodule_path": "vendor/hygen-create",
            "root": str(root),
        },
        "checkpoints": results,
        "failures": failures,
        "standing": standing,
        "claim_ceiling": "REAL_GGEN_BINARY_P0_P6_CONSEQUENCE_ONLY",
        "note": (
            "Proves P0-P6 against a real ggen binary. Does NOT close the P7 crown "
            "(HYGEN_CREATE_PARITY_ALIVE) - that additionally requires a reference_dir "
            "produced by the real upstream `hygen` render step, not attempted here. "
            "See ROADMAP.md's 80/20 ERRC section."
        ),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "replay": {
            "command": (
                "python3 scripts/gall_ggen_binary_parity.py --root . "
                "--receipt ggen-binary-parity-receipt.json"
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
