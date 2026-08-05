#!/usr/bin/env python3
"""GALL surface observations and executing negative fixtures."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True

from ci_router import RoutingRefusal, route_paths
from gall_contract import CheckpointFailure, Context, run, sample_receipt, validate_receipt, verify_clean_tree, verify_exact_head


def scan_docs(root: Path) -> dict[str, Any]:
    paths = [root / "README.md", root / "BOOTSTRAP.md", *sorted(root.glob("docs/**/*.md"))]
    admitted: list[str] = []
    failures: list[str] = []
    for path in paths:
        relative = str(path.relative_to(root))
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"invalid-utf8:{relative}")
            continue
        if "\0" in text or not text.strip():
            failures.append(f"empty-or-nul:{relative}")
        else:
            admitted.append(relative)
    if failures:
        raise CheckpointFailure("BUILD_BROKEN:DOCS_INTEGRITY", ";".join(failures))
    return {"admitted": admitted, "count": len(admitted)}


def scan_ontology(root: Path) -> dict[str, Any]:
    surface = root / "ontology"
    allowed = {".ttl", ".trig", ".nq", ".nt", ".jsonld", ".rdf", ".owl", ".keep"}
    if not surface.is_dir():
        raise CheckpointFailure("BUILD_BROKEN:ONTOLOGY_SURFACE_MISSING", "ontology/")
    admitted: list[str] = []
    failures: list[str] = []
    for path in sorted(surface.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in allowed and path.name != ".keep":
            failures.append(f"unsupported:{relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"invalid-utf8:{relative}")
            continue
        if path.name != ".keep" and not text.strip():
            failures.append(f"empty:{relative}")
        else:
            admitted.append(relative)
    if failures:
        raise CheckpointFailure("BUILD_BROKEN:ONTOLOGY_SURFACE", ";".join(failures))
    substantive = [path for path in admitted if not path.endswith("/.keep")]
    return {
        "admitted": admitted,
        "substantive_count": len(substantive),
        "bootstrap_empty_surface": not substantive,
    }


def scan_build(root: Path) -> dict[str, Any]:
    if not (root / "Cargo.toml").is_file():
        candidates = (root / "Cargo.lock", root / "build.rs", root / "src", root / "crates")
        orphans = [str(path.relative_to(root)) for path in candidates if path.exists()]
        if orphans:
            raise CheckpointFailure("BUILD_BROKEN:ORPHAN_BUILD_SURFACE", ",".join(orphans))
        return {"mode": "bootstrap-absence", "manifest": None, "orphan_surfaces": []}
    if not shutil.which("cargo"):
        raise CheckpointFailure("UNSUPPORTED:CARGO_MISSING", "Cargo.toml exists but cargo is unavailable")
    commands = [
        ["cargo", "fmt", "--all", "--", "--check"],
        ["cargo", "check", "--workspace", "--all-targets"],
        ["cargo", "test", "--workspace", "--all-targets"],
    ]
    for index, command in enumerate(commands):
        completed = run(command, root)
        if completed.returncode:
            raise CheckpointFailure(
                f"BUILD_BROKEN:BUILD_COMMAND_{index}_FAILED",
                (completed.stderr or completed.stdout)[-4000:],
            )
    return {"mode": "cargo", "manifest": "Cargo.toml", "commands": commands}


def expect_failure(call: Callable[[], Any], code: str) -> dict[str, Any]:
    try:
        call()
    except (CheckpointFailure, RoutingRefusal) as error:
        observed = error.code if isinstance(error, CheckpointFailure) else error.reason
        if observed != code:
            raise CheckpointFailure(
                "BUILD_BROKEN:NEGATIVE_FALSIFIER_WRONG_FAILURE",
                f"expected={code} observed={observed}",
            )
        return {
            "passed": True,
            "expected_failure": code,
            "observed_failure": observed,
            "detail": error.detail,
        }
    raise CheckpointFailure("BUILD_BROKEN:NEGATIVE_FALSIFIER_ACCEPTED", code)


def git_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "GALL",
        "GIT_AUTHOR_EMAIL": "gall@example.invalid",
        "GIT_COMMITTER_NAME": "GALL",
        "GIT_COMMITTER_EMAIL": "gall@example.invalid",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, env=env, check=True)
    return holder, root


def negative_exact(context: Context) -> dict[str, Any]:
    return expect_failure(lambda: verify_exact_head(context.root, "0" * 40), "REFUSED:HEAD_IDENTITY_MISMATCH")


def negative_clean(_: Context) -> dict[str, Any]:
    holder, root = git_fixture()
    try:
        (root / "dirty").write_text("x", encoding="utf-8")
        return expect_failure(lambda: verify_clean_tree(root), "REFUSED:DIRTY_WORKTREE")
    finally:
        holder.cleanup()


def negative_routing(_: Context) -> dict[str, Any]:
    return expect_failure(lambda: route_paths(["../escape"]), "REFUSED:INVALID_CHANGED_PATH")


def negative_ci(context: Context) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bad.py"
        path.write_text("def broken(:\n", encoding="utf-8")
        completed = run([sys.executable, "-m", "py_compile", str(path)], context.root)
        if not completed.returncode:
            raise CheckpointFailure("BUILD_BROKEN:NEGATIVE_FALSIFIER_ACCEPTED", "invalid Python compiled")
        return {
            "passed": True,
            "expected_failure": "BUILD_BROKEN:PYTHON_SYNTAX",
            "observed_failure": "BUILD_BROKEN:PYTHON_SYNTAX",
            "detail": completed.stderr[-4000:],
        }


def negative_docs(_: Context) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "docs").mkdir()
        (root / "README.md").write_text("# x\n", encoding="utf-8")
        (root / "BOOTSTRAP.md").write_text("x\n", encoding="utf-8")
        (root / "docs" / "empty.md").write_text("", encoding="utf-8")
        return expect_failure(lambda: scan_docs(root), "BUILD_BROKEN:DOCS_INTEGRITY")


def negative_ontology(_: Context) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "ontology").mkdir()
        (root / "ontology" / "bad.exe").write_text("x", encoding="utf-8")
        return expect_failure(lambda: scan_ontology(root), "BUILD_BROKEN:ONTOLOGY_SURFACE")


def negative_build(_: Context) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "src").mkdir()
        return expect_failure(lambda: scan_build(root), "BUILD_BROKEN:ORPHAN_BUILD_SURFACE")


def negative_receipt(context: Context) -> dict[str, Any]:
    payload = sample_receipt(context.head)
    payload.pop("negative_falsifier")
    return expect_failure(lambda: validate_receipt(payload), "BUILD_BROKEN:RECEIPT_FIELDS_MISSING")
