from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .cases import render_concrete, values_for
from .model import GgenCreateError, SESSION_FILE
from .package import build_package, rewrite_package_parameter
from .session import admitted_files, load_session

ORIGINAL_SESSION_FILE = "hygen-create.json"
_REFERENCE_SESSION_CANONICAL_PATH = ".ggen-create-reference/capture-session.json"


def tree_manifest(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def compare_trees(left: Path, right: Path) -> dict[str, Any]:
    left_map = tree_manifest(left)
    right_map = tree_manifest(right)
    left_paths = set(left_map)
    right_paths = set(right_map)
    differing = sorted(
        path
        for path in left_paths & right_paths
        if left_map[path] != right_map[path]
    )
    return {
        "equal": left_map == right_map,
        "only_left": sorted(left_paths - right_paths),
        "only_right": sorted(right_paths - left_paths),
        "different": differing,
    }


def _canonical_capture_document(raw: bytes, *, source_name: str) -> bytes:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GgenCreateError(
            "REFERENCE_CAPTURE_PARSE_REFUSED",
            f"{source_name}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise GgenCreateError(
            "REFERENCE_CAPTURE_SCHEMA_REFUSED",
            f"{source_name}: capture document must be an object",
        )
    files = value.get("files_and_dirs")
    if not isinstance(files, dict):
        raise GgenCreateError(
            "REFERENCE_CAPTURE_SCHEMA_REFUSED",
            f"{source_name}: files_and_dirs must be an object",
        )

    normalized_files: dict[str, Any] = {}
    for path, included in files.items():
        canonical_path = SESSION_FILE if path == ORIGINAL_SESSION_FILE else path
        if canonical_path in normalized_files and normalized_files[canonical_path] != included:
            raise GgenCreateError(
                "REFERENCE_CAPTURE_ALIAS_COLLISION_REFUSED",
                f"{source_name}: conflicting entries for {canonical_path}",
            )
        normalized_files[canonical_path] = included

    normalized = dict(value)
    normalized["files_and_dirs"] = normalized_files
    # Tool release identity is intentionally not artifact semantics. The exact
    # reference identity is carried separately by reference_id in the report.
    if "hygen_create_version" in normalized:
        normalized["hygen_create_version"] = "<capture-tool-version>"
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _reference_manifest(root: Path) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    manifest = tree_manifest(root)
    aliases = [name for name in (ORIGINAL_SESSION_FILE, SESSION_FILE) if name in manifest]
    if len(aliases) > 1:
        raise GgenCreateError(
            "REFERENCE_CAPTURE_ALIAS_COLLISION_REFUSED",
            f"{root} contains both {ORIGINAL_SESSION_FILE} and {SESSION_FILE}",
        )
    normalizations: list[dict[str, str]] = []
    if aliases:
        source_name = aliases[0]
        raw = manifest.pop(source_name)
        manifest[_REFERENCE_SESSION_CANONICAL_PATH] = _canonical_capture_document(
            raw,
            source_name=source_name,
        )
        normalizations.append(
            {
                "source": source_name,
                "canonical": _REFERENCE_SESSION_CANONICAL_PATH,
                "policy": "capture-session-semantic-v1",
            }
        )
    return manifest, normalizations


def compare_reference_trees(left: Path, right: Path) -> dict[str, Any]:
    left_map, left_normalizations = _reference_manifest(left)
    right_map, right_normalizations = _reference_manifest(right)
    left_paths = set(left_map)
    right_paths = set(right_map)
    differing = sorted(
        path
        for path in left_paths & right_paths
        if left_map[path] != right_map[path]
    )
    return {
        "equal": left_map == right_map,
        "only_left": sorted(left_paths - right_paths),
        "only_right": sorted(right_paths - left_paths),
        "different": differing,
        "normalizations": {
            "left": left_normalizations,
            "right": right_normalizations,
        },
        "policy": "byte-exact-except-capture-session-semantic-v1",
    }


def _expected_artifacts(session_path: Path, value: str) -> dict[str, bytes]:
    session = load_session(session_path)
    seed = session["templatize_using_name"]
    if not seed:
        raise GgenCreateError("PARAMETER_NOT_SEEDED_REFUSED", "missing seed")
    root = session_path.parent
    expected: dict[str, bytes] = {}
    for rel in admitted_files(session_path):
        target, _ = render_concrete(rel, seed, value)
        if session["gen_parent_dir"]:
            target = values_for(value)["name"] + "/" + target
        source = (root / rel).read_text(encoding="utf-8")
        rendered, _ = render_concrete(source, seed, value)
        expected[target] = rendered.encode("utf-8")
    return expected


def _write_artifact_projection(
    run_dir: Path,
    artifact_dir: Path,
    expected: dict[str, bytes],
) -> None:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    for rel, expected_bytes in expected.items():
        source = run_dir / rel
        if not source.is_file():
            raise GgenCreateError("EXPECTED_OUTPUT_MISSING_REFUSED", rel)
        actual = source.read_bytes()
        if actual != expected_bytes:
            raise GgenCreateError("RECONSTRUCTION_DRIFT_REFUSED", rel)
        target = artifact_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(actual)


def _run_ggen(
    package_dir: Path,
    ggen_bin: str,
    sync_args: list[str],
) -> dict[str, Any]:
    command = [ggen_bin, *sync_args]
    completed = subprocess.run(
        command,
        cwd=package_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise GgenCreateError(
            "GGEN_EXECUTION_REFUSED",
            json.dumps(result, indent=2),
        )
    return result


def _run_behavior(
    cwd: Path,
    command: str,
    stdout_contains: str | None,
    value: str,
) -> dict[str, Any]:
    substitutions = values_for(value)
    rendered_command = command
    for key, replacement in substitutions.items():
        rendered_command = rendered_command.replace("{" + key + "}", replacement)
    completed = subprocess.run(
        rendered_command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    result = {
        "command": rendered_command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise GgenCreateError(
            "BEHAVIOR_COMMAND_REFUSED",
            json.dumps(result, indent=2),
        )
    if stdout_contains is not None:
        expected = stdout_contains
        for key, replacement in substitutions.items():
            expected = expected.replace("{" + key + "}", replacement)
        if expected not in completed.stdout:
            raise GgenCreateError(
                "BEHAVIOR_ASSERTION_REFUSED",
                f"stdout does not contain {expected!r}: {completed.stdout!r}",
            )
        result["stdout_contains"] = expected
    return result


def _write_report(output_root: Path, report: dict[str, Any]) -> Path:
    report_path = output_root / "parity-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report_path


def verify_parity(
    session_path: Path,
    *,
    output_root: Path,
    ggen_bin: str,
    variation_value: str,
    sync_args: list[str] | None = None,
    behavior_command: str | None = None,
    stdout_contains: str | None = None,
    reference_dir: Path | None = None,
    reference_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    session = load_session(session_path)
    seed = session["templatize_using_name"]
    if not seed:
        raise GgenCreateError("PARAMETER_NOT_SEEDED_REFUSED", "missing seed")
    # Identifier admission must occur before resolving, deleting, or creating
    # the verifier output directory.
    values_for(variation_value)
    sync_args = sync_args or ["sync", "run"]

    output_root = output_root.resolve()
    if output_root.exists():
        if not force:
            raise GgenCreateError(
                "VERIFY_OUTPUT_EXISTS_REFUSED",
                f"use --force to replace {output_root}",
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    package_build_root = output_root / "package"
    build = build_package(session_path, package_build_root)
    base_package = build.package_dir

    revision_source = output_root / "revision-source"
    revision_source.mkdir(parents=True)
    for rel in admitted_files(session_path):
        source = session_path.parent / rel
        target = revision_source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    revision_session = revision_source / session_path.name
    revision_packages = output_root / "revision-packages"
    revision_first = build_package(revision_session, revision_packages)
    revision_repeat = build_package(revision_session, revision_packages)
    if revision_repeat.changed:
        raise GgenCreateError(
            "IDENTICAL_REVISION_DRIFT_REFUSED",
            "identical generator unexpectedly produced a new revision",
        )
    mutation_target = next(
        (
            revision_source / rel
            for rel in admitted_files(revision_session)
            if rel != revision_session.name
        ),
        None,
    )
    if mutation_target is None:
        raise GgenCreateError(
            "REVISION_FIXTURE_MISSING_REFUSED",
            "revision parity requires one admitted exemplar besides the session file",
        )
    mutation_target.write_text(
        mutation_target.read_text(encoding="utf-8")
        + "\n# ggen-create revision checkpoint\n",
        encoding="utf-8",
    )
    revision_changed = build_package(revision_session, revision_packages)
    if not revision_changed.changed or revision_changed.archived_previous is None:
        raise GgenCreateError(
            "REVISION_ARCHIVE_REFUSED",
            "changed exemplar did not archive the previous generator",
        )
    revision_check = {
        "first_package": str(revision_first.package_dir),
        "identical_repeat_changed": revision_repeat.changed,
        "changed_package": str(revision_changed.package_dir),
        "archived_previous": str(revision_changed.archived_previous),
    }

    executions: dict[str, Any] = {}
    artifacts: dict[str, str] = {}
    for label, value in (
        ("reconstruction", seed),
        ("variation", variation_value),
    ):
        run_dir = output_root / f"{label}-run"
        artifact_dir = output_root / f"{label}-artifact"
        shutil.copytree(base_package, run_dir)
        rewrite_package_parameter(run_dir, value)
        execution = _run_ggen(run_dir, ggen_bin, sync_args)
        expected = _expected_artifacts(session_path, value)
        _write_artifact_projection(run_dir, artifact_dir, expected)
        executions[label] = execution
        artifacts[label] = str(artifact_dir)

    behavior: dict[str, Any] | None = None
    if behavior_command:
        behavior = _run_behavior(
            Path(artifacts["variation"]),
            behavior_command,
            stdout_contains,
            variation_value,
        )

    reference_comparison: dict[str, Any] | None = None
    reference_equal = True
    if reference_dir is not None:
        reference_comparison = compare_reference_trees(
            reference_dir.resolve(),
            Path(artifacts["variation"]),
        )
        reference_equal = bool(reference_comparison["equal"])

    crown_requested = reference_dir is not None and bool(reference_id)
    checkpoints = {
        "P0_REFERENCE_IDENTITY": "ALIVE" if crown_requested else "UNEXECUTED",
        "P1_CAPTURE_PARITY": "ALIVE",
        "P2_TRANSFORMATION_PARITY": "ALIVE",
        "P3_INSPECTION_PARITY": "ALIVE",
        "P4_RECONSTRUCTION_PARITY": "ALIVE",
        "P5_VARIATION_PARITY": "ALIVE",
        "P6_REVISION_PARITY": "ALIVE",
        "P7_PARITY_CROWN": (
            "ALIVE"
            if crown_requested and reference_equal
            else "REFUSED"
            if crown_requested
            else "PARTIAL_ALIVE"
        ),
    }
    report = {
        "schema": "ggen-create-parity-report/0.2",
        "state": (
            "ALIVE"
            if checkpoints["P7_PARITY_CROWN"] == "ALIVE"
            else "REFUSED"
            if checkpoints["P7_PARITY_CROWN"] == "REFUSED"
            else "PARTIAL_ALIVE"
        ),
        "generator": session["name"],
        "seed": seed,
        "variation": variation_value,
        "ggen": {"binary": ggen_bin, "sync_args": sync_args},
        "executions": executions,
        "artifacts": artifacts,
        "behavior": behavior,
        "reference": {
            "identity": reference_id,
            "directory": str(reference_dir) if reference_dir else None,
        },
        "reference_comparison": reference_comparison,
        "revision_check": revision_check,
        "checkpoints": checkpoints,
    }
    report_path = _write_report(output_root, report)
    report["report_path"] = str(report_path)

    if crown_requested and not reference_equal:
        raise GgenCreateError(
            "REFERENCE_PARITY_DRIFT_REFUSED",
            json.dumps(
                {
                    **(reference_comparison or {}),
                    "report_path": str(report_path),
                },
                indent=2,
            ),
        )
    return report
