from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from .inspect import inspect_session
from .integrity import verify_package
from .model import GgenCreateError
from .package import build_package
from .runtime import (
    ReceiptStore,
    atomic_write_json,
    digest_file,
    digest_json,
    utc_now,
)
from .session import admitted_files, load_session
from .verify import verify_parity


def session_fingerprint(session_path: Path) -> dict[str, Any]:
    session = load_session(session_path)
    root = session_path.parent
    files = {
        rel: digest_file(root / rel)
        for rel in admitted_files(session_path)
    }
    subject = {
        "session": digest_file(session_path),
        "files": files,
        "generator": session["name"],
        "seed": session["templatize_using_name"],
        "gen_parent_dir": session["gen_parent_dir"],
    }
    return {**subject, "digest": digest_json(subject)}


def _state_path(session_path: Path) -> Path:
    return session_path.parent / ".ggen-create" / "automatic-state.json"


def load_automatic_state(session_path: Path) -> dict[str, Any] | None:
    path = _state_path(session_path)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError("AUTOMATIC_STATE_REFUSED", str(exc)) from exc
    if not isinstance(value, dict):
        raise GgenCreateError(
            "AUTOMATIC_STATE_REFUSED",
            "automatic state must be an object",
        )
    return value


def automatic_plan(
    session_path: Path,
    *,
    output_root: Path,
    variation_value: str | None = None,
    verify: bool = False,
) -> dict[str, Any]:
    session_path = session_path.resolve()
    report = inspect_session(session_path)
    if report["replacement_count"] == 0:
        raise GgenCreateError(
            "NO_GENERALIZATION_REFUSED",
            "the admitted exemplar contains no occurrences of the seeded parameter",
        )
    fingerprint = session_fingerprint(session_path)
    actions = [
        {
            "action": "package.build",
            "authority": "DO_INTENT",
            "requires_confirmation": True,
            "arguments": {"output_root": str(output_root.resolve())},
        }
    ]
    if verify:
        if not variation_value:
            raise GgenCreateError(
                "VARIATION_REQUIRED_REFUSED",
                "automatic verification requires a non-empty variation value",
            )
        actions.append(
            {
                "action": "parity.verify",
                "authority": "DO_INTENT",
                "requires_confirmation": True,
                "arguments": {"variation_value": variation_value},
            }
        )
    return {
        "schema": "ggen-create-automatic-plan/0.2",
        "created_at": utc_now(),
        "session": str(session_path),
        "generator": report["generator"],
        "fingerprint": fingerprint,
        "inspection": report,
        "actions": actions,
        "state": "CANDIDATE",
    }


def run_automatic(
    session_path: Path,
    *,
    output_root: Path,
    apply: bool = False,
    confirm: bool = False,
    verify: bool = False,
    ggen_bin: str = "ggen",
    variation_value: str | None = None,
    sync_args: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    session_path = session_path.resolve()
    output_root = output_root.resolve()
    plan = automatic_plan(
        session_path,
        output_root=output_root,
        variation_value=variation_value,
        verify=verify,
    )
    if not apply:
        return {**plan, "state": "PARTIAL_ALIVE", "executed": []}
    if not confirm:
        raise GgenCreateError(
            "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
            "automatic apply requires confirm=true",
        )

    build = build_package(session_path, output_root, force=force)
    integrity = verify_package(build.package_dir)
    if not integrity["valid"]:
        raise GgenCreateError(
            "PACKAGE_INTEGRITY_REFUSED",
            json.dumps(integrity, sort_keys=True),
        )
    executed: list[dict[str, Any]] = [
        {
            "action": "package.build",
            "package": str(build.package_dir),
            "changed": build.changed,
            "archived_previous": (
                str(build.archived_previous)
                if build.archived_previous
                else None
            ),
            "receipt": str(build.receipt_path),
            "integrity": integrity,
        }
    ]
    parity: dict[str, Any] | None = None
    if verify:
        assert variation_value is not None
        verification_root = output_root / ".verification"
        parity = verify_parity(
            session_path,
            output_root=verification_root,
            ggen_bin=ggen_bin,
            variation_value=variation_value,
            sync_args=sync_args,
            force=True,
        )
        executed.append(
            {
                "action": "parity.verify",
                "report": parity["report_path"],
                "checkpoints": parity["checkpoints"],
            }
        )

    state = {
        "schema": "ggen-create-automatic-state/0.2",
        "updated_at": utc_now(),
        "session": str(session_path),
        "fingerprint": plan["fingerprint"],
        "package": str(build.package_dir),
        "package_changed": build.changed,
        "package_integrity": integrity,
        "parity_report": parity["report_path"] if parity else None,
    }
    state_path = _state_path(session_path)
    atomic_write_json(state_path, state)
    receipt = ReceiptStore(session_path.parent).append(
        operation="automatic.create",
        state="ALIVE",
        inputs={
            "session": str(session_path),
            "fingerprint": plan["fingerprint"]["digest"],
            "verify": verify,
            "variation": variation_value,
        },
        outputs={
            "package": str(build.package_dir),
            "changed": build.changed,
            "integrity": integrity,
            "state": str(state_path),
            "parity": parity["report_path"] if parity else None,
        },
    )
    return {
        **plan,
        "state": "ALIVE",
        "executed": executed,
        "automatic_state": str(state_path),
        "receipt": receipt,
    }


def watch_automatic(
    session_path: Path,
    *,
    output_root: Path,
    cycles: int = 1,
    interval_seconds: float = 0.0,
    confirm: bool = False,
    verify: bool = False,
    ggen_bin: str = "ggen",
    variation_value: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    session_path = session_path.resolve()
    output_root = output_root.resolve()
    if cycles < 1 or cycles > 100:
        raise GgenCreateError(
            "WATCH_CYCLES_REFUSED",
            "cycles must be in [1, 100]",
        )
    if interval_seconds < 0 or interval_seconds > 3600:
        raise GgenCreateError(
            "WATCH_INTERVAL_REFUSED",
            "interval must be between 0 and 3600 seconds",
        )
    if not confirm:
        raise GgenCreateError(
            "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
            "automatic watch writes state and receipts and requires confirm=true",
        )

    recorded = load_automatic_state(session_path)
    previous = (
        recorded.get("fingerprint", {}).get("digest")
        if recorded is not None
        else None
    )
    recorded_package = (
        Path(str(recorded.get("package")))
        if recorded and recorded.get("package")
        else None
    )
    history: list[dict[str, Any]] = []
    for index in range(cycles):
        fingerprint = session_fingerprint(session_path)["digest"]
        integrity = (
            verify_package(recorded_package)
            if recorded_package is not None
            else {"valid": False, "reason": "PACKAGE_UNRECORDED"}
        )
        changed = fingerprint != previous or not integrity["valid"]
        if changed:
            result = run_automatic(
                session_path,
                output_root=output_root,
                apply=True,
                confirm=True,
                verify=verify,
                ggen_bin=ggen_bin,
                variation_value=variation_value,
                force=force,
            )
            recorded_package = Path(result["executed"][0]["package"])
            history.append(
                {
                    "cycle": index + 1,
                    "fingerprint": fingerprint,
                    "state": result["state"],
                    "reason": (
                        "FINGERPRINT_CHANGED"
                        if fingerprint != previous
                        else "PACKAGE_INTEGRITY_DRIFT"
                    ),
                    "executed": result["executed"],
                }
            )
            previous = fingerprint
        else:
            history.append(
                {
                    "cycle": index + 1,
                    "fingerprint": fingerprint,
                    "state": "STABLE",
                    "reason": None,
                    "integrity": integrity,
                    "executed": [],
                }
            )
        if interval_seconds and index + 1 < cycles:
            time.sleep(interval_seconds)

    converged = bool(history and history[-1]["state"] == "STABLE")
    report = {
        "schema": "ggen-create-automatic-watch/0.2",
        "state": "ALIVE",
        "converged": converged,
        "cycles": history,
    }
    report_path = (
        session_path.parent / ".ggen-create" / "automatic-watch-report.json"
    )
    atomic_write_json(report_path, report)
    receipt = ReceiptStore(session_path.parent).append(
        operation="automatic.watch",
        state="ALIVE",
        inputs={
            "session": str(session_path),
            "output_root": str(output_root),
            "cycles": cycles,
            "interval_seconds": interval_seconds,
            "verify": verify,
        },
        outputs={
            "report": str(report_path),
            "converged": converged,
            "executed_cycles": sum(
                1 for item in history if item["executed"]
            ),
        },
    )
    report["report_path"] = str(report_path)
    report["receipt"] = receipt
    return report
