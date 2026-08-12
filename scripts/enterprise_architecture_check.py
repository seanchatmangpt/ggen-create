#!/usr/bin/env python3
"""Enforce the admitted enterprise architecture contract for ggen-dspy."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

SCHEMA = "ggen-create.enterprise-architecture.receipt.v1"


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "passed": passed,
        "detail": detail,
        "typed_failure": None
        if passed
        else f"BUILD_BROKEN:ENTERPRISE_ARCHITECTURE_{check_id.upper()}_FAILED",
    }


def evaluate(root: Path) -> dict[str, Any]:
    contract_path = root / "architecture" / "enterprise.toml"
    checks: list[dict[str, Any]] = []

    if not contract_path.is_file():
        checks.append(_check("contract_present", False, str(contract_path)))
        return _receipt(root, {}, checks)

    try:
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:
        checks.append(_check("contract_parse", False, str(exc)))
        return _receipt(root, {}, checks)

    checks.append(_check("contract_parse", True, contract.get("schema", "")))
    checks.append(
        _check(
            "schema",
            contract.get("schema") == "ggen-create.enterprise-architecture.v1",
            str(contract.get("schema")),
        )
    )
    checks.append(
        _check(
            "status",
            contract.get("status") == "ADMITTED",
            str(contract.get("status")),
        )
    )

    subject = contract.get("subject", {})
    component = subject.get("component", "")
    crate_root = root / component
    crate_manifest = crate_root / "Cargo.toml"
    checks.append(_check("component_present", crate_root.is_dir(), component))
    checks.append(_check("manifest_present", crate_manifest.is_file(), str(crate_manifest)))

    required_docs = contract.get("controls", {}).get("required_docs", [])
    missing_docs = [rel for rel in required_docs if not (root / rel).is_file()]
    checks.append(
        _check(
            "required_docs",
            not missing_docs,
            "all present" if not missing_docs else "missing: " + ", ".join(missing_docs),
        )
    )

    checks.append(_check("lockfile", (root / "Cargo.lock").is_file(), "Cargo.lock"))
    toolchain_path = root / "rust-toolchain.toml"
    toolchain_ok = False
    toolchain_detail = "missing rust-toolchain.toml"
    if toolchain_path.is_file():
        try:
            toolchain = tomllib.loads(toolchain_path.read_text(encoding="utf-8"))
            channel = str(toolchain.get("toolchain", {}).get("channel", ""))
            toolchain_ok = bool(channel) and channel not in {"stable", "beta", "nightly"}
            toolchain_detail = channel or "empty channel"
        except Exception as exc:
            toolchain_detail = str(exc)
    checks.append(_check("pinned_toolchain", toolchain_ok, toolchain_detail))

    manifest: dict[str, Any] = {}
    if crate_manifest.is_file():
        try:
            manifest = tomllib.loads(crate_manifest.read_text(encoding="utf-8"))
            checks.append(_check("manifest_parse", True, "Cargo.toml parsed"))
        except Exception as exc:
            checks.append(_check("manifest_parse", False, str(exc)))

    package = manifest.get("package", {})
    checks.append(
        _check(
            "publish_disabled",
            package.get("publish") is False,
            f"publish={package.get('publish')!r}",
        )
    )

    dependencies = manifest.get("dependencies", {})
    expected_deps = int(contract.get("supply_chain", {}).get("runtime_dependencies", -1))
    actual_deps = len(dependencies) if isinstance(dependencies, dict) else -1
    checks.append(
        _check(
            "runtime_dependencies",
            actual_deps == expected_deps,
            f"expected={expected_deps} actual={actual_deps}",
        )
    )

    rust_files = sorted((crate_root / "src").glob("**/*.rs")) if crate_root.is_dir() else []
    source = "\n".join(path.read_text(encoding="utf-8") for path in rust_files)
    checks.append(_check("rust_source_present", bool(rust_files), f"files={len(rust_files)}"))

    required_markers = contract.get("controls", {}).get("required_rust_markers", [])
    missing_markers = [marker for marker in required_markers if marker not in source]
    checks.append(
        _check(
            "authority_markers",
            not missing_markers,
            "all present" if not missing_markers else "missing: " + ", ".join(missing_markers),
        )
    )

    forbidden_markers = contract.get("controls", {}).get("forbidden_rust_markers", [])
    found_forbidden = [marker for marker in forbidden_markers if marker in source]
    checks.append(
        _check(
            "ambient_authority",
            not found_forbidden,
            "none found" if not found_forbidden else "found: " + ", ".join(found_forbidden),
        )
    )

    authority = contract.get("authority", {})
    authority_ok = (
        authority.get("actuate") is False
        and authority.get("zero_unreceipted_actuation") is True
        and authority.get("model_output_is_authority") is False
        and bool(authority.get("exclusive_do_owner"))
    )
    checks.append(
        _check(
            "authority_contract",
            authority_ok,
            json.dumps(authority, sort_keys=True),
        )
    )

    return _receipt(root, contract, checks)


def _receipt(root: Path, contract: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = bool(checks) and all(item["passed"] for item in checks)
    return {
        "schema": SCHEMA,
        "repository": contract.get("subject", {}).get("repository", "seanchatmangpt/ggen-create"),
        "head": _git_head(root),
        "contract": "architecture/enterprise.toml",
        "contract_version": contract.get("version", "UNKNOWN"),
        "checks": checks,
        "standing": "ALIVE" if passed else "BUILD_BROKEN",
        "typed_failure": None if passed else "BUILD_BROKEN:ENTERPRISE_ARCHITECTURE_CONFORMANCE_FAILED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--receipt", default="enterprise-architecture-receipt.json")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    receipt = evaluate(root)
    encoded = json.dumps(receipt, indent=2, sort_keys=True)
    print(encoded)
    if args.receipt:
        Path(args.receipt).write_text(encoded + "\n", encoding="utf-8")
    return 0 if receipt["standing"] == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
