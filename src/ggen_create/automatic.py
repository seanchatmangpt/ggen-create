from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from .inspect import inspect_session
from .model import GgenCreateError
from .package import build_package
from .runtime import ReceiptStore, atomic_write_json, digest_file, digest_json, utc_now
from .session import admitted_files, load_session
from .verify import verify_parity


def session_fingerprint(session_path: Path) -> dict[str, Any]:
    session = load_session(session_path)
    root = session_path.parent
    files = {rel: digest_file(root / rel) for rel in admitted_files(session_path)}
    subject = {
        "session": digest_file(session_path),
        "files": files,
        "generator": session["name"],
        "seed": session["templatize_using_name"],
        "gen_parent_dir": session["gen_parent_dir"],
    }
    return {**subject, "digest": digest_json(subject)}


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
        "schema": "ggen-create-automatic-plan/0.1",
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
    executed: list[dict[str, Any]] = [
        {
            "action": "package.build",
            "package": str(build.package_dir),
            "changed": build.changed,
            "archived_previous": str(build.archived_previous)
            if build.archived_previous
            else None,
            "receipt": str(build.receipt_path),
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

    state_dir = session_path.parent / ".ggen-create"
    state = {
        "schema": "ggen-create-automatic-state/0.1",
        "updated_at": utc_now(),
        "session": str(session_path),
        "fingerprint": plan["fingerprint"],
        "package": str(build.package_dir),
        "package_changed": build.changed,
        "parity_report": parity["report_path"] if parity else None,
    }
    state_path = state_dir / "automatic-state.json"
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
) -> dict[str, Any]:
    if cycles < 1 or cycles > 100:
        raise GgenCreateError("WATCH_CYCLES_REFUSED", "cycles must be in [1, 100]")
    if interval_seconds < 0 or interval_seconds > 3600:
        raise GgenCreateError(
            "WATCH_INTERVAL_REFUSED", "interval must be between 0 and 3600 seconds"
        )
    history: list[dict[str, Any]] = []
    previous: str | None = None
    for index in range(cycles):
        fingerprint = session_fingerprint(session_path)["digest"]
        if fingerprint != previous:
            result = run_automatic(
                session_path,
                output_root=output_root,
                apply=True,
                confirm=confirm,
                verify=verify,
                ggen_bin=ggen_bin,
                variation_value=variation_value,
            )
            history.append(
                {
                    "cycle": index + 1,
                    "fingerprint": fingerprint,
                    "state": result["state"],
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
                    "executed": [],
                }
            )
        if interval_seconds and index + 1 < cycles:
            time.sleep(interval_seconds)
    return {
        "schema": "ggen-create-automatic-watch/0.1",
        "state": "ALIVE",
        "cycles": history,
        "converged": bool(history and history[-1]["state"] == "STABLE"),
    }
