"""Cutover skills: plan, power, verify, rollback over declared env-file targets.

`cutover-targets.json` (in the subject root) declares which `KEY=value` lines flip from
the legacy backend to the target backend. Power rewrites exactly those lines atomically
after taking a content-addressed backup; rollback restores the backups byte-for-byte and
refuses if a target drifted since power. Nothing here removes, archives or decommissions
any backend; sunset is a separate, separately authorized actuation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .model import GgenCreateError

PREREQS = "cutover-prerequisites.json"
TARGETS = "cutover-targets.json"
STATE = "cutover-state.json"
TARGETS_SCHEMA = "ggen.create.cutover.targets.v1"
LEGACY = "legacy"
POWERED = "target"

# prerequisite key -> typed refusal code
PREFLIGHT_REFUSALS = {
    "migrations_applied": "PREFLIGHT_MIGRATIONS_NOT_APPLIED_REFUSED",
    "auth_bridge_configured": "PREFLIGHT_AUTH_BRIDGE_UNCONFIGURED_REFUSED",
    "tripwire_green": "PREFLIGHT_TRIPWIRE_RED_REFUSED",
    "release_admitted": "PREFLIGHT_RELEASE_NOT_ADMITTED_REFUSED",
    "two_probe_identity": "PREFLIGHT_IDENTITY_PROBE_FAILED_REFUSED",
    "write_freeze_declared": "PREFLIGHT_WRITE_FREEZE_UNDECLARED_REFUSED",
}

STEPS = ("preflight", "write_freeze", "delta_sync", "flip_origin", "verify", "sign_off")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file():
        raise GgenCreateError(code, f"missing {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GgenCreateError(code, f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GgenCreateError(code, f"{path}: expected an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _atomic_write(path: Path, data: bytes) -> None:
    """Write beside the target then os.replace; preserves an existing file's mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o7777 if path.exists() else None
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def preflight(subject_root: Path) -> dict[str, Any]:
    """Refuse (typed, with broken_term) unless every prerequisite holds."""
    declared = _load(subject_root / PREREQS, "PREFLIGHT_PREREQUISITES_MISSING_REFUSED")
    for key, code in PREFLIGHT_REFUSALS.items():
        if declared.get(key) is not True:
            raise GgenCreateError(code, f"broken_term={key}")
    return {key: True for key in PREFLIGHT_REFUSALS}


def _line_re(key: str) -> re.Pattern[str]:
    return re.compile(rf"^(?P<head>\s*(?:export\s+)?{re.escape(key)}\s*=\s*)(?P<value>.*?)(?P<tail>\s*)$",
                      re.MULTILINE)


def load_targets(subject_root: Path) -> dict[str, Any]:
    spec = _load(subject_root / TARGETS, "TARGETS_MISSING_REFUSED")
    if spec.get("schema") != TARGETS_SCHEMA:
        raise GgenCreateError("TARGETS_SCHEMA_REFUSED", f"expected {TARGETS_SCHEMA}")
    targets = spec.get("targets")
    if not isinstance(targets, list) or not targets:
        raise GgenCreateError("TARGETS_EMPTY_REFUSED", "targets must be a non-empty list")
    predecessors = {str(p) for p in spec.get("predecessors", [])}
    root = subject_root.resolve()
    seen: set[tuple[str, str]] = set()
    for item in targets:
        for field in ("file", "key", "from", "to"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise GgenCreateError("TARGET_FIELD_REFUSED", f"{field} missing in {item}")
        raw = root / item["file"]
        if raw.is_symlink() or any(p.is_symlink() for p in raw.parents if p != root and root in p.parents):
            raise GgenCreateError("TARGET_SYMLINK_REFUSED", item["file"])
        resolved = raw.resolve()
        if root not in resolved.parents:
            raise GgenCreateError("TARGET_PATH_ESCAPE_REFUSED", item["file"])
        if predecessors & set(resolved.relative_to(root).parts):
            raise GgenCreateError("TARGET_IN_PREDECESSOR_REFUSED", item["file"])
        ident = (item["file"], item["key"])
        if ident in seen:
            raise GgenCreateError("TARGET_DUPLICATE_REFUSED", f"{ident}")
        seen.add(ident)
    return spec


def _current_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise GgenCreateError("TARGET_FILE_MISSING_REFUSED", str(path))
    matches = list(_line_re(key).finditer(path.read_text(encoding="utf-8")))
    if not matches:
        raise GgenCreateError("TARGET_KEY_MISSING_REFUSED", f"{path}:{key}")
    if len(matches) > 1:
        raise GgenCreateError("TARGET_KEY_AMBIGUOUS_REFUSED", f"{path}:{key}")
    return matches[0].group("value")


def _check_targets(subject_root: Path, spec: dict[str, Any], expect: str) -> None:
    for item in spec["targets"]:
        value = _current_value(subject_root / item["file"], item["key"])
        if value != item[expect]:
            raise GgenCreateError(
                "TARGET_VALUE_MISMATCH_REFUSED",
                f"{item['file']}:{item['key']} is {value!r}, expected {item[expect]!r}",
            )


def plan_cutover(subject_root: Path, output_root: Path, dry_run: bool = True) -> dict[str, Any]:
    """CONSTRUCT: deterministic ordered steps; reads files, writes none."""
    del dry_run  # plan never writes; the flag exists for CLI symmetry
    inputs = preflight(subject_root)
    spec = load_targets(subject_root)
    state_path = output_root / STATE
    state: dict[str, Any] = (
        _load(state_path, "STATE_INVALID_REFUSED") if state_path.exists() else {"active": LEGACY}
    )
    if state.get("active") == POWERED:
        raise GgenCreateError("ALREADY_POWERED_REFUSED", "targets already flipped")
    _check_targets(subject_root, spec, "from")
    body = {
        "schema": "ggen.create.cutover.plan.v1",
        "preflight_inputs": inputs,
        "targets": [{k: t[k] for k in ("file", "key", "from", "to")} for t in spec["targets"]],
        "steps": [{"order": i + 1, "step": s} for i, s in enumerate(STEPS)],
        "rollback": "restore content-addressed backups; refuse on drift",
    }
    body["plan_digest"] = _digest(body)
    return body


def power_cutover(subject_root: Path, output_root: Path) -> dict[str, Any]:
    """DO_INTENT: flip every target after preflight; all-or-nothing."""
    preflight(subject_root)
    spec = load_targets(subject_root)
    state_path = output_root / STATE
    state: dict[str, Any] = (
        _load(state_path, "STATE_INVALID_REFUSED") if state_path.exists() else {"active": LEGACY}
    )
    if state.get("active") == POWERED:
        raise GgenCreateError("ALREADY_POWERED_REFUSED", "targets already flipped")
    _check_targets(subject_root, spec, "from")

    by_file: dict[str, list[dict[str, Any]]] = {}
    for item in spec["targets"]:
        by_file.setdefault(item["file"], []).append(item)

    records: list[dict[str, Any]] = []
    written: list[tuple[Path, bytes]] = []
    try:
        for file, items in by_file.items():
            path = subject_root / file
            before = path.read_bytes()
            backup = output_root / "backups" / (_sha(before).split(":")[1] + ".bak")
            if not backup.exists():
                _atomic_write(backup, before)
            text = before.decode("utf-8")
            for item in items:
                text = _line_re(item["key"]).sub(
                    lambda m, to=item["to"]: f"{m.group('head')}{to}{m.group('tail')}", text, count=1)
            after = text.encode("utf-8")
            _atomic_write(path, after)
            written.append((path, before))
            records.append({
                "file": file,
                "keys": [{k: i[k] for k in ("key", "from", "to")} for i in items],
                "sha256_before": _sha(before), "sha256_after": _sha(after),
                "backup": str(backup.relative_to(output_root)),
            })
        _write_json(state_path, {"active": POWERED, "targets": records})
    except BaseException as exc:
        for path, before in reversed(written):
            _atomic_write(path, before)
        if isinstance(exc, GgenCreateError):
            raise
        raise GgenCreateError("POWER_ABORTED_ROLLED_BACK", f"{type(exc).__name__}: {exc}") from exc
    return {"state_file": str(state_path), "targets": records, "state": "PARTIAL_ALIVE"}


def rollback_cutover(subject_root: Path, output_root: Path) -> dict[str, Any]:
    """DO_INTENT: byte-exact inverse of power; refuses if a target drifted since."""
    state_path = output_root / STATE
    state = _load(state_path, "STATE_MISSING_REFUSED")
    if state.get("active") != POWERED or not isinstance(state.get("targets"), list):
        raise GgenCreateError("NOTHING_TO_ROLL_BACK_REFUSED", "targets are not flipped")
    for rec in state["targets"]:
        current = _sha((subject_root / rec["file"]).read_bytes())
        if current != rec["sha256_after"]:
            raise GgenCreateError("TARGET_DRIFT_REFUSED", f"{rec['file']} changed since power")
        backup = output_root / rec["backup"]
        if not backup.is_file() or _sha(backup.read_bytes()) != rec["sha256_before"]:
            raise GgenCreateError("BACKUP_INTEGRITY_REFUSED", rec["backup"])
    for rec in state["targets"]:
        _atomic_write(subject_root / rec["file"], (output_root / rec["backup"]).read_bytes())
    restored = {"active": LEGACY, "rolled_back_from": _digest(state)}
    _write_json(state_path, restored)
    return {"state_file": str(state_path), "restored": [r["file"] for r in state["targets"]],
            "state": "PARTIAL_ALIVE"}


def verify_cutover(subject_root: Path, output_root: Path, replay: bool = False) -> dict[str, Any]:
    """SELECT: report standing; with replay, recompute digests and refuse on drift."""
    state_path = output_root / STATE
    state: dict[str, Any] = (
        _load(state_path, "STATE_MISSING_REFUSED") if state_path.exists() else {"active": LEGACY}
    )
    drift: list[str] = []
    if replay and state.get("active") == POWERED:
        for rec in state["targets"]:
            path = subject_root / rec["file"]
            if not path.is_file() or _sha(path.read_bytes()) != rec["sha256_after"]:
                drift.append(rec["file"])
            backup = output_root / rec["backup"]
            if not backup.is_file() or _sha(backup.read_bytes()) != rec["sha256_before"]:
                drift.append(rec["backup"])
    if drift:
        raise GgenCreateError("REPLAY_DRIFT_REFUSED", json.dumps(sorted(set(drift))))
    return {
        "active": state.get("active"),
        "rollback_available": state.get("active") == POWERED,
        "state_digest": _digest(state),
        "replayed": bool(replay),
        "state": "ALIVE",
    }
