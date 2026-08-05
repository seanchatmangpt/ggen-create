from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .a2a import A2A_PROTOCOL_VERSION
from .agents import AGENTS
from .automatic import load_automatic_state
from .integrity import verify_package
from .mcp import MCP_PROTOCOL_VERSION
from .model import APP_VERSION, GgenCreateError, SESSION_FILE
from .runtime import ReceiptStore, TaskStore
from .session import find_session
from .skills import SKILLS, Broker, SkillRegistry


def refusal(exc: GgenCreateError) -> dict[str, Any]:
    return {
        "state": "REFUSED",
        "refusal": exc.code,
        "detail": exc.detail,
    }


def doctor_report(
    root: Path,
    *,
    project: str = SESSION_FILE,
) -> dict[str, Any]:
    root = root.resolve()
    checks: dict[str, Any] = {
        "runtime": {
            "state": "ALIVE",
            "version": APP_VERSION,
            "mcp_protocol": MCP_PROTOCOL_VERSION,
            "a2a_protocol": A2A_PROTOCOL_VERSION,
        },
        "authority": {
            "state": (
                "ALIVE"
                if all(not skill.may_actuate for skill in SKILLS)
                and all(not agent.may_actuate for agent in AGENTS)
                else "REFUSED"
            ),
            "skill_count": len(SKILLS),
            "agent_count": len(AGENTS),
        },
    }

    session_path: Path | None = None
    try:
        session_path = find_session(root, project)
        inspection = Broker(root).execute(
            SkillRegistry().plan("capture.inspect", {}),
            session_path=session_path,
        )
        checks["capture"] = {
            "state": "ALIVE",
            "session": str(session_path),
            "generator": inspection["result"]["generator"],
            "file_count": inspection["result"]["file_count"],
            "replacement_count": inspection["result"]["replacement_count"],
        }
    except GgenCreateError as exc:
        checks["capture"] = {
            "state": "BLOCKED",
            "refusal": exc.code,
            "detail": exc.detail,
        }

    receipts = ReceiptStore(root)
    try:
        latest = receipts.latest()
        chain = receipts.verify_chain()
        if latest is None:
            checks["receipts"] = {
                "state": "PARTIAL_ALIVE",
                "count": 0,
                "latest": None,
                "chain": chain,
            }
        else:
            latest_check = ReceiptStore.verify(Path(latest["path"]))
            checks["receipts"] = {
                "state": (
                    "ALIVE"
                    if latest_check["valid"] and chain["valid"]
                    else "REFUSED"
                ),
                "count": chain["count"],
                "latest": latest_check,
                "chain": chain,
            }
    except GgenCreateError as exc:
        checks["receipts"] = refusal(exc)

    if session_path is None:
        checks["package"] = {
            "state": "UNKNOWN",
            "reason": "NO_CAPTURE_SESSION",
        }
    else:
        try:
            automatic_state = load_automatic_state(session_path)
            package = (
                Path(str(automatic_state["package"]))
                if automatic_state and automatic_state.get("package")
                else None
            )
            if package is None:
                checks["package"] = {
                    "state": "PARTIAL_ALIVE",
                    "reason": "NO_AUTOMATIC_PACKAGE_RECORDED",
                }
            else:
                integrity = verify_package(package)
                checks["package"] = {
                    "state": (
                        "ALIVE" if integrity["valid"] else "REFUSED"
                    ),
                    "integrity": integrity,
                }
        except GgenCreateError as exc:
            checks["package"] = refusal(exc)

    task_checks: dict[str, Any] = {}
    for namespace in ("mcp", "a2a"):
        try:
            store = TaskStore(root, namespace)
            pruned = store.prune()
            values = store.list()
            status_values = sorted(
                {str(item.get("status")) for item in values}
            )
            task_checks[namespace] = {
                "state": "ALIVE",
                "count": len(values),
                "pruned": pruned,
                "status_counts": {
                    status: sum(
                        1
                        for item in values
                        if item.get("status") == status
                    )
                    for status in status_values
                },
            }
        except GgenCreateError as exc:
            task_checks[namespace] = refusal(exc)
    checks["tasks"] = {
        "state": (
            "REFUSED"
            if any(
                item.get("state") == "REFUSED"
                for item in task_checks.values()
            )
            else "ALIVE"
        ),
        "namespaces": task_checks,
    }

    states = [
        value.get("state")
        for value in checks.values()
        if isinstance(value, dict) and "state" in value
    ]
    if "REFUSED" in states:
        state = "REFUSED"
    elif "BLOCKED" in states:
        state = "BLOCKED"
    elif "UNKNOWN" in states or "PARTIAL_ALIVE" in states:
        state = "PARTIAL_ALIVE"
    else:
        state = "ALIVE"
    return {
        "schema": "ggen-create-doctor/0.2",
        "root": str(root),
        "state": state,
        "checks": checks,
    }


def format_doctor(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)
