from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from .legacy_embedded import replay_script, verify_script
from .legacy_model import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_FILES,
    DEFAULT_PRODUCER_REPOSITORY,
    MANIFEST_SCHEMA,
    RECEIPT_SCHEMA,
    UNKNOWN_PRODUCER_COMMIT,
    LegacyBuildResult,
    iter_legacy_files,
    plan_legacy_factory,
    receiving_contract,
    render_ontology,
    render_readme,
)
from .model import GgenCreateError
from .runtime import atomic_write_json, digest_file, digest_json, require_under


def _bundle_file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    }


def _bundle_file_modes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): f"{stat.S_IMODE(path.stat().st_mode):04o}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    }


def _subject_drift(manifest: dict[str, Any], subject: Path, bundle: Path) -> list[dict[str, str]]:
    admitted = {
        item["path"]: item
        for item in manifest.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    observed: set[str] = set()
    drift: list[dict[str, str]] = []
    try:
        for path in iter_legacy_files(subject, bundle):
            observed.add(path.relative_to(subject).as_posix())
    except GgenCreateError as exc:
        drift.append({"path": exc.detail, "reason": exc.code})
    for relative, item in admitted.items():
        path = subject / relative
        if relative not in observed:
            drift.append({"path": relative, "reason": "missing"})
            continue
        try:
            metadata = path.stat()
            current_digest = digest_file(path)
        except OSError:
            drift.append({"path": relative, "reason": "read"})
            continue
        if current_digest != item.get("sha256"):
            drift.append({"path": relative, "reason": "digest"})
        elif f"{stat.S_IMODE(metadata.st_mode):04o}" != item.get("mode"):
            drift.append({"path": relative, "reason": "mode"})
        elif metadata.st_size != item.get("size"):
            drift.append({"path": relative, "reason": "size"})
    for relative in sorted(observed - set(admitted)):
        drift.append({"path": relative, "reason": "unadmitted"})
    return drift


def verify_legacy_bundle(bundle_root: Path, *, subject_root: Path | None = None) -> dict[str, Any]:
    root = bundle_root.resolve()
    try:
        receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        contract = json.loads((root / "receiving-contract.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError("LEGACY_BUNDLE_PARSE_REFUSED", str(exc)) from exc
    actual = _bundle_file_digests(root)
    actual_modes = _bundle_file_modes(root)
    expected = receipt.get("outputs")
    expected_modes = receipt.get("output_modes")
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    checks: dict[str, bool] = {
        "receipt_schema": receipt.get("schema") == RECEIPT_SCHEMA,
        "manifest_schema": manifest.get("schema") == MANIFEST_SCHEMA,
        "output_set": isinstance(expected, dict) and set(actual) == set(expected),
        "output_digests": isinstance(expected, dict) and actual == expected,
        "output_modes": isinstance(expected_modes, dict) and actual_modes == expected_modes,
        "receipt_digest": digest_json(payload) == receipt.get("receipt_digest"),
        "subject_digest_binding": manifest.get("subject", {}).get("digest") == receipt.get("subject_digest"),
        "producer_identity_binding": (
            manifest.get("producer_identity")
            == contract.get("producer_identity")
            == receipt.get("producer_identity")
        ),
    }
    drift: list[dict[str, str]] = []
    if subject_root is not None:
        drift = _subject_drift(manifest, subject_root.resolve(), root)
        checks["subject_replay"] = not drift
    valid = all(checks.values())
    return {
        "bundle": str(root),
        "valid": valid,
        "checks": checks,
        "drift": drift,
        "subject_digest": receipt.get("subject_digest"),
        "bundle_digest": receipt.get("bundle_digest"),
        "state": "ALIVE" if valid else "BUILD_BROKEN",
    }


def build_legacy_bundle(
    subject_root: Path,
    output_root: Path,
    *,
    program_id: str = "ggen-legacy-foundry",
    producer_repository: str = DEFAULT_PRODUCER_REPOSITORY,
    producer_commit: str = UNKNOWN_PRODUCER_COMMIT,
    force: bool = False,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> LegacyBuildResult:
    subject = subject_root.resolve()
    output = require_under(subject, output_root)
    if output == subject:
        raise GgenCreateError("OUTPUT_ROOT_REFUSED", "output root cannot equal subject root")
    manifest = plan_legacy_factory(
        subject,
        output_root=output,
        program_id=program_id,
        producer_repository=producer_repository,
        producer_commit=producer_commit,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    contract = receiving_contract(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        atomic_write_json(staging / "manifest.json", manifest)
        atomic_write_json(staging / "receiving-contract.json", contract)
        (staging / "ontology.ttl").write_text(render_ontology(manifest), encoding="utf-8")
        (staging / "README.md").write_text(render_readme(manifest), encoding="utf-8")
        (staging / "verify_bundle.py").write_text(verify_script(), encoding="utf-8")
        (staging / "replay_bundle.py").write_text(replay_script(), encoding="utf-8")
        os.chmod(staging / "verify_bundle.py", 0o755)
        os.chmod(staging / "replay_bundle.py", 0o755)
        (staging / "ggen.toml").write_text(
            "[project]\nname = \"" + manifest["program_id"] + "\"\n\n"
            "[ontology]\nsource = \"ontology.ttl\"\n\n"
            "[templates]\ndir = \"templates\"\naggregate_modules = true\n\n"
            "[law]\nreflexive = true\n",
            encoding="utf-8",
        )
        (staging / "templates").mkdir()
        (staging / "templates" / ".keep").write_text("", encoding="utf-8")
        outputs = _bundle_file_digests(staging)
        output_modes = _bundle_file_modes(staging)
        bundle_digest = digest_json({"outputs": outputs, "output_modes": output_modes})
        receipt_payload = {
            "schema": RECEIPT_SCHEMA,
            "operation": "legacy.power",
            "state": "PARTIAL_ALIVE",
            "program_id": manifest["program_id"],
            "producer_identity": manifest["producer_identity"],
            "subject_digest": manifest["subject"]["digest"],
            "bundle_digest": bundle_digest,
            "outputs": outputs,
            "output_modes": output_modes,
            "claims": {
                "observation": "ALIVE",
                "receiving_contract": "ALIVE",
                "ontology_projection": "ALIVE",
                "ggen_execution": "UNKNOWN",
                "behavioral_equivalence": "UNKNOWN",
                "release": "UNKNOWN",
                "sunset": "UNKNOWN",
            },
        }
        receipt = {**receipt_payload, "receipt_digest": digest_json(receipt_payload)}
        atomic_write_json(staging / "receipt.json", receipt)
        if output.exists():
            current_receipt = output / "receipt.json"
            if current_receipt.is_file():
                try:
                    current = json.loads(current_receipt.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    current = {}
                if (
                    current.get("bundle_digest") == bundle_digest
                    and current.get("subject_digest") == manifest["subject"]["digest"]
                    and current.get("producer_identity") == manifest["producer_identity"]
                ):
                    return LegacyBuildResult(output, False, current_receipt, manifest["subject"]["digest"], bundle_digest)
            if not force:
                raise GgenCreateError("LEGACY_OUTPUT_EXISTS_REFUSED", str(output))
            if output.is_symlink():
                raise GgenCreateError("LEGACY_OUTPUT_SYMLINK_REFUSED", str(output))
            shutil.rmtree(output)
        os.replace(staging, output)
        staging = None
        verification = verify_legacy_bundle(output, subject_root=subject)
        if not verification["valid"]:
            raise GgenCreateError("LEGACY_BUNDLE_INTEGRITY_REFUSED", json.dumps(verification, sort_keys=True))
        return LegacyBuildResult(output, True, output / "receipt.json", manifest["subject"]["digest"], bundle_digest)
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
