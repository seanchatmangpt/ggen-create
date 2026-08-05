from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .model import GgenCreateError

PACKAGE_RECEIPT_SCHEMA = "ggen-create-package-receipt/0.2"
LEGACY_PACKAGE_RECEIPT_SCHEMA = "ggen-create-parity-receipt/0.1"


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def _hash_json(value: Any) -> str:
    data = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _safe_relative_path(value: str) -> bool:
    if not value or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if normalized in {".", ".."}:
        return False
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return False
    return not any(part == ".." for part in posix.parts)


def _invalid(
    package_dir: Path,
    reason: str,
    *,
    detail: Any = None,
    missing: list[str] | None = None,
    extra: list[str] | None = None,
    different: list[str] | None = None,
    symlinks: list[str] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "valid": False,
        "package": str(package_dir),
        "reason": reason,
        "missing": missing or [],
        "extra": extra or [],
        "different": different or [],
        "symlinks": symlinks or [],
        "receipt_valid": False,
    }
    if detail is not None:
        value["detail"] = detail
    return value


def verify_package(package_dir: Path) -> dict[str, Any]:
    package_dir = package_dir.resolve()
    receipt_path = package_dir / "receipt.json"
    if not package_dir.is_dir():
        return _invalid(package_dir, "PACKAGE_MISSING")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_MISSING",
            missing=["receipt.json"],
        )
    except (OSError, json.JSONDecodeError) as exc:
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_INVALID",
            detail=str(exc),
        )
    if not isinstance(receipt, dict):
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_SCHEMA",
            detail="receipt must be an object",
        )

    schema = receipt.get("schema")
    if schema not in {PACKAGE_RECEIPT_SCHEMA, LEGACY_PACKAGE_RECEIPT_SCHEMA}:
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_SCHEMA",
            detail=f"unsupported schema: {schema!r}",
        )
    if receipt.get("algorithm") != "sha256":
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_SCHEMA",
            detail="algorithm must be sha256",
        )

    expected = receipt.get("files")
    if not isinstance(expected, dict) or not expected:
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_SCHEMA",
            detail="files must be a non-empty object",
        )
    unsafe_expected = sorted(
        key
        for key in expected
        if not isinstance(key, str) or not _safe_relative_path(key)
    )
    invalid_hashes = sorted(
        key
        for key, value in expected.items()
        if not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    )
    if unsafe_expected or invalid_hashes:
        return _invalid(
            package_dir,
            "PACKAGE_RECEIPT_SCHEMA",
            detail={
                "unsafe_paths": unsafe_expected,
                "invalid_hashes": invalid_hashes,
            },
        )

    receipt_valid = True
    claimed_digest = receipt.get("receipt_digest")
    computed_digest: str | None = None
    if schema == PACKAGE_RECEIPT_SCHEMA:
        payload = {
            key: value
            for key, value in receipt.items()
            if key != "receipt_digest"
        }
        computed_digest = _hash_json(payload)
        receipt_valid = (
            isinstance(claimed_digest, str)
            and claimed_digest == computed_digest
        )

    symlinks = sorted(
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_symlink()
    )
    actual_paths = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path != receipt_path
    }
    expected_paths = set(expected)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    different = sorted(
        rel
        for rel in expected_paths & actual_paths
        if _hash_file(package_dir / rel) != expected[rel]
    )
    valid = (
        receipt_valid
        and not symlinks
        and not missing
        and not extra
        and not different
    )
    return {
        "valid": valid,
        "package": str(package_dir),
        "receipt": str(receipt_path),
        "reason": None if valid else "PACKAGE_INTEGRITY_DRIFT",
        "missing": missing,
        "extra": extra,
        "different": different,
        "symlinks": symlinks,
        "generator": receipt.get("generator"),
        "operation": receipt.get("operation"),
        "parameter_value": receipt.get("parameter_value"),
        "parent": receipt.get("parent"),
        "receipt_valid": receipt_valid,
        "claimed_receipt_digest": claimed_digest,
        "computed_receipt_digest": computed_digest,
    }


def require_valid_package(package_dir: Path) -> dict[str, Any]:
    result = verify_package(package_dir)
    if not result["valid"]:
        raise GgenCreateError(
            "PACKAGE_INTEGRITY_REFUSED",
            json.dumps(result, indent=2, sort_keys=True),
        )
    return result
