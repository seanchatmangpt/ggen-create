from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from .automatic import automatic_plan, run_automatic, session_fingerprint
from .integrity import verify_package
from .model import GgenCreateError
from .runtime import ReceiptStore, atomic_write_json, utc_now
from .session import load_session


@dataclass(frozen=True)
class AutonomicPolicy:
    max_cycles: int = 4
    stable_cycles: int = 2
    interval_seconds: float = 0.0
    apply: bool = False
    confirm: bool = False
    verify: bool = False
    variation_value: str | None = None
    ggen_bin: str = "ggen"

    def validate(self) -> None:
        if not 1 <= self.max_cycles <= 100:
            raise GgenCreateError(
                "AUTONOMIC_CYCLES_REFUSED",
                "max_cycles must be in [1, 100]",
            )
        if not 1 <= self.stable_cycles <= self.max_cycles:
            raise GgenCreateError(
                "AUTONOMIC_STABILITY_REFUSED",
                "stable_cycles must be in [1, max_cycles]",
            )
        if not 0 <= self.interval_seconds <= 3600:
            raise GgenCreateError(
                "AUTONOMIC_INTERVAL_REFUSED",
                "interval_seconds must be between 0 and 3600",
            )
        if self.apply and not self.confirm:
            raise GgenCreateError(
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
                "autonomic apply requires confirm=true",
            )


def _knowledge_path(session_path: Path) -> Path:
    return session_path.parent / ".ggen-create" / "autonomic-knowledge.json"


def _load_knowledge(session_path: Path) -> dict[str, Any]:
    path = _knowledge_path(session_path)
    if not path.is_file():
        return {
            "schema": "ggen-create-autonomic-knowledge/0.2",
            "cycles": [],
            "last_fingerprint": None,
            "last_package": None,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError("AUTONOMIC_KNOWLEDGE_REFUSED", str(exc)) from exc
    if not isinstance(value, dict) or not isinstance(value.get("cycles"), list):
        raise GgenCreateError(
            "AUTONOMIC_KNOWLEDGE_REFUSED",
            "invalid knowledge document",
        )
    return value


def monitor(session_path: Path, output_root: Path) -> dict[str, Any]:
    session_path = session_path.resolve()
    session = load_session(session_path)
    fingerprint = session_fingerprint(session_path)
    package = output_root.resolve() / session["name"]
    automatic_state = (
        session_path.parent / ".ggen-create" / "automatic-state.json"
    )
    recorded: dict[str, Any] | None = None
    state_error: str | None = None
    if automatic_state.is_file():
        try:
            value = json.loads(automatic_state.read_text(encoding="utf-8"))
            recorded = value if isinstance(value, dict) else None
            if recorded is None:
                state_error = "AUTOMATIC_STATE_SCHEMA_REFUSED"
        except (OSError, json.JSONDecodeError) as exc:
            state_error = f"AUTOMATIC_STATE_PARSE_REFUSED: {exc}"
    integrity = verify_package(package)
    return {
        "timestamp": utc_now(),
        "session": str(session_path),
        "generator": session["name"],
        "seeded": bool(session["templatize_using_name"]),
        "fingerprint": fingerprint,
        "package": str(package),
        "package_exists": package.is_dir(),
        "package_integrity": integrity,
        "automatic_state_error": state_error,
        "recorded_fingerprint": (
            recorded.get("fingerprint", {}).get("digest")
            if recorded
            else None
        ),
    }


def analyze(observation: dict[str, Any]) -> dict[str, Any]:
    if not observation["seeded"]:
        return {
            "condition": "INPUT_REQUIRED",
            "state": "BLOCKED",
            "reason": "PARAMETER_NOT_SEEDED_REFUSED",
        }
    if not observation["package_exists"]:
        return {
            "condition": "PACKAGE_ABSENT",
            "state": "PARTIAL_ALIVE",
            "reason": "PACKAGE_BUILD_REQUIRED",
        }
    if not observation["package_integrity"]["valid"]:
        return {
            "condition": "PACKAGE_CORRUPT",
            "state": "PARTIAL_ALIVE",
            "reason": "PACKAGE_INTEGRITY_REPAIR_REQUIRED",
        }
    if observation["automatic_state_error"]:
        return {
            "condition": "KNOWLEDGE_DRIFT",
            "state": "PARTIAL_ALIVE",
            "reason": observation["automatic_state_error"],
        }
    if (
        observation["recorded_fingerprint"]
        != observation["fingerprint"]["digest"]
    ):
        return {
            "condition": "EXEMPLAR_DRIFT",
            "state": "PARTIAL_ALIVE",
            "reason": "PACKAGE_REBUILD_REQUIRED",
        }
    return {"condition": "STABLE", "state": "ALIVE", "reason": None}


def plan(
    session_path: Path,
    output_root: Path,
    analysis: dict[str, Any],
    policy: AutonomicPolicy,
) -> dict[str, Any]:
    if analysis["condition"] == "INPUT_REQUIRED":
        return {
            "action": "request-input",
            "arguments": {"required": "parameter seed"},
            "requires_confirmation": False,
        }
    if analysis["condition"] in {
        "PACKAGE_ABSENT",
        "PACKAGE_CORRUPT",
        "KNOWLEDGE_DRIFT",
        "EXEMPLAR_DRIFT",
    }:
        candidate = automatic_plan(
            session_path,
            output_root=output_root,
            variation_value=policy.variation_value,
            verify=policy.verify,
        )
        return {
            "action": "automatic.create",
            "arguments": candidate,
            "requires_confirmation": True,
            "reason": analysis["condition"],
        }
    return {
        "action": "none",
        "arguments": {},
        "requires_confirmation": False,
    }


def _persist_cycle(
    session_path: Path,
    cycle: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    knowledge = _load_knowledge(session_path)
    knowledge["schema"] = "ggen-create-autonomic-knowledge/0.2"
    knowledge["cycles"].append(cycle)
    knowledge["cycles"] = knowledge["cycles"][-100:]
    knowledge["last_fingerprint"] = observation["fingerprint"]["digest"]
    knowledge["last_package"] = observation["package"]
    knowledge["updated_at"] = utc_now()
    atomic_write_json(_knowledge_path(session_path), knowledge)


def autonomic_cycle(
    session_path: Path,
    *,
    output_root: Path,
    policy: AutonomicPolicy,
) -> dict[str, Any]:
    policy.validate()
    session_path = session_path.resolve()
    output_root = output_root.resolve()
    observation = monitor(session_path, output_root)
    diagnosis = analyze(observation)
    action_plan = plan(session_path, output_root, diagnosis, policy)
    execution: dict[str, Any] | None = None

    if action_plan["action"] == "automatic.create" and policy.apply:
        try:
            execution = run_automatic(
                session_path,
                output_root=output_root,
                apply=True,
                confirm=policy.confirm,
                verify=policy.verify,
                ggen_bin=policy.ggen_bin,
                variation_value=policy.variation_value,
            )
            observation = monitor(session_path, output_root)
            diagnosis = analyze(observation)
        except GgenCreateError as exc:
            execution = {
                "state": "BLOCKED",
                "refusal": exc.code,
                "detail": exc.detail,
            }
            diagnosis = {
                "condition": "EXECUTION_BLOCKED",
                "state": "BLOCKED",
                "reason": exc.code,
            }
    elif action_plan["action"] == "automatic.create":
        execution = {
            "state": "PARTIAL_ALIVE",
            "reason": "APPLY_NOT_AUTHORIZED",
        }
    elif action_plan["action"] == "request-input":
        execution = {
            "state": "BLOCKED",
            "refusal": "PARAMETER_NOT_SEEDED_REFUSED",
        }

    cycle = {
        "schema": "ggen-create-autonomic-cycle/0.2",
        "timestamp": utc_now(),
        "monitor": observation,
        "analyze": diagnosis,
        "plan": action_plan,
        "execute": execution,
        "state": diagnosis["state"],
    }
    _persist_cycle(session_path, cycle, observation)
    return cycle


def run_autonomic(
    session_path: Path,
    *,
    output_root: Path,
    policy: AutonomicPolicy,
) -> dict[str, Any]:
    policy.validate()
    session_path = session_path.resolve()
    output_root = output_root.resolve()
    cycles: list[dict[str, Any]] = []
    stable_count = 0
    for index in range(policy.max_cycles):
        cycle = autonomic_cycle(
            session_path,
            output_root=output_root,
            policy=policy,
        )
        cycle["cycle"] = index + 1
        cycles.append(cycle)
        if cycle["analyze"]["condition"] == "STABLE":
            stable_count += 1
        else:
            stable_count = 0
        if stable_count >= policy.stable_cycles:
            break
        if cycle["state"] == "BLOCKED":
            break
        if policy.interval_seconds and index + 1 < policy.max_cycles:
            time.sleep(policy.interval_seconds)

    converged = stable_count >= policy.stable_cycles
    if converged:
        state = "ALIVE"
    elif cycles and cycles[-1]["state"] == "BLOCKED":
        state = "BLOCKED"
    else:
        state = "PARTIAL_ALIVE"
    report = {
        "schema": "ggen-create-autonomic-report/0.2",
        "state": state,
        "converged": converged,
        "stable_cycles": stable_count,
        "cycle_ceiling_reached": (
            len(cycles) >= policy.max_cycles and not converged
        ),
        "cycles": cycles,
        "knowledge": str(_knowledge_path(session_path)),
    }
    report_path = (
        session_path.parent / ".ggen-create" / "autonomic-report.json"
    )
    atomic_write_json(report_path, report)
    receipt = ReceiptStore(session_path.parent).append(
        operation="autonomic.run",
        state=state,
        inputs={
            "session": str(session_path),
            "output_root": str(output_root),
            "policy": {
                "max_cycles": policy.max_cycles,
                "stable_cycles": policy.stable_cycles,
                "interval_seconds": policy.interval_seconds,
                "apply": policy.apply,
                "verify": policy.verify,
                "variation_value": policy.variation_value,
                "ggen_bin": policy.ggen_bin,
            },
        },
        outputs={
            "report": str(report_path),
            "converged": converged,
            "cycle_count": len(cycles),
        },
    )
    report["report_path"] = str(report_path)
    report["receipt"] = receipt
    return report
