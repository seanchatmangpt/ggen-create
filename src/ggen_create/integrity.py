from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .model import GgenCreateError


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def verify_package(package_dir: Path) -> dict[str, Any]:
    package_dir = package_dir.resolve()
    receipt_path = package_dir / "receipt.json"
    if not package_dir.is_dir():
        return {
            "valid": False,
            "package": str(package_dir),
            "reason": "PACKAGE_MISSING",
            "missing": [],
            "extra": [],
            "different": [],
        }
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "valid": False,
            "package": str(package_dir),
            "reason": "PACKAGE_RECEIPT_MISSING",
            "missing": ["receipt.json"],
            "extra": [],
            "different": [],
        }
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "package": str(package_dir),
            "reason": "PACKAGE_RECEIPT_INVALID",
            "detail": str(exc),
            "missing": [],
            "extra": [],
            "different": [],
        }
    expected = receipt.get("files")
    if not isinstance(expected, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in expected.items()
    ):
        raise GgenCreateError(
            "PACKAGE_RECEIPT_SCHEMA_REFUSED",
            str(receipt_path),
        )
    actual_paths = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file() and path != receipt_path
    }
    expected_paths = set(expected)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    different = sorted(
        rel
        for rel in expected_paths & actual_paths
        if _hash_file(package_dir / rel) != expected[rel]
    )
    valid = not missing and not extra and not different
    return {
        "valid": valid,
        "package": str(package_dir),
        "receipt": str(receipt_path),
        "reason": None if valid else "PACKAGE_INTEGRITY_DRIFT",
        "missing": missing,
        "extra": extra,
        "different": different,
        "generator": receipt.get("generator"),
    }
