"""Shared MCP tool execution logic for the FastMCP server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp.tools import ToolResult

from .agents import AgentRuntime
from .model import GgenCreateError, SESSION_FILE
from .runtime import ReceiptStore
from .session import find_session
from .skills import Broker, SkillRegistry

_GLOBAL_TO_SKILL = {
    "ggen_create_agent_route": "agents.route",
    "ggen_create_receipt_verify": "receipt.verify",
    "ggen_create_receipt_chain_verify": "receipt.chain.verify",
    "ggen_create_doctor": "doctor.inspect",
}


def tool_success(value: Any) -> ToolResult:
    structured = value if isinstance(value, dict) else {"value": value}
    return ToolResult(
        content=[
            {
                "type": "text",
                "text": json.dumps(
                    structured,
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            }
        ],
        structured_content=structured,
    )


def tool_refusal(exc: GgenCreateError) -> ToolResult:
    payload = {"code": exc.code, "detail": exc.detail}
    return ToolResult(
        content=[
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True),
            }
        ],
        structured_content=payload,
        is_error=True,
    )


def tool_internal_error(exc: Exception) -> ToolResult:
    payload = {
        "code": "TOOL_INTERNAL_ERROR",
        "type": type(exc).__name__,
        "detail": str(exc),
    }
    return ToolResult(
        content=[
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True),
            }
        ],
        structured_content=payload,
        is_error=True,
    )


class McpService:
    """Root-scoped broker surface for ggen-create MCP tools."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.registry = SkillRegistry()
        self.agents = AgentRuntime(self.root)

    def session_path(self, project: str = SESSION_FILE) -> Path:
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError(
                "PROJECT_NAME_REFUSED",
                "project must be a capture filename",
            )
        return find_session(self.root, project)

    def execute_skill(
        self,
        skill_name: str,
        arguments: dict[str, Any],
        *,
        session_path: Path | None,
        confirm: bool = False,
    ) -> ToolResult:
        try:
            value = Broker(self.root).execute(
                self.registry.plan(skill_name, arguments),
                session_path=session_path,
                confirm=confirm,
            )
            return tool_success(value)
        except GgenCreateError as exc:
            return tool_refusal(exc)
        except Exception as exc:
            return tool_internal_error(exc)

    def execute_named(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        normalized = dict(arguments)
        if name == "ggen_create_package_verify" and normalized.get("package") is None:
            normalized.pop("package", None)

        skill_name = _GLOBAL_TO_SKILL.get(name)
        if skill_name is not None:
            return self.execute_skill(
                skill_name,
                normalized,
                session_path=None,
            )

        try:
            session_path = self.session_path(str(normalized.get("project", SESSION_FILE)))
            broker = Broker(self.root)
            confirm = bool(normalized.get("confirm", False))

            if name == "ggen_create_status":
                value = broker.execute(
                    self.registry.plan("capture.inspect", {}),
                    session_path=session_path,
                )
            elif name == "ggen_create_automatic_plan":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.plan",
                        {
                            "output_root": normalized.get("output_root", "_ggen"),
                            "verify": bool(normalized.get("verify", False)),
                            "variation_value": normalized.get("variation_value"),
                        },
                    ),
                    session_path=session_path,
                )
            elif name == "ggen_create_package_verify":
                value = broker.execute(
                    self.registry.plan(
                        "package.verify",
                        {
                            "output_root": normalized.get("output_root", "_ggen"),
                            "package": normalized.get("package"),
                        },
                    ),
                    session_path=session_path,
                )
            elif name == "ggen_create_apply":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.create",
                        {
                            "output_root": normalized.get("output_root", "_ggen"),
                            "verify": bool(normalized.get("verify", False)),
                            "variation_value": normalized.get("variation_value"),
                            "ggen_bin": normalized.get("ggen_bin", "ggen"),
                            "force": bool(normalized.get("force", False)),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_automatic_watch":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.watch",
                        {
                            "output_root": normalized.get("output_root", "_ggen"),
                            "cycles": int(normalized.get("cycles", 2)),
                            "interval_seconds": float(
                                normalized.get("interval_seconds", 0)
                            ),
                            "verify": bool(normalized.get("verify", False)),
                            "variation_value": normalized.get("variation_value"),
                            "ggen_bin": normalized.get("ggen_bin", "ggen"),
                            "force": bool(normalized.get("force", False)),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name in {
                "ggen_create_autonomic_cycle",
                "ggen_create_autonomic_run",
            }:
                skill = (
                    "autonomic.cycle"
                    if name.endswith("cycle")
                    else "autonomic.run"
                )
                value = broker.execute(
                    self.registry.plan(
                        skill,
                        {
                            "output_root": normalized.get("output_root", "_ggen"),
                            "max_cycles": int(normalized.get("max_cycles", 4)),
                            "stable_cycles": int(
                                normalized.get("stable_cycles", 2)
                            ),
                            "interval_seconds": float(
                                normalized.get("interval_seconds", 0)
                            ),
                            "apply": bool(normalized.get("apply", True)),
                            "verify": bool(normalized.get("verify", False)),
                            "variation_value": normalized.get("variation_value"),
                            "ggen_bin": normalized.get("ggen_bin", "ggen"),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_agent_dispatch":
                value = self.agents.dispatch(
                    str(normalized.get("agent", "")),
                    str(normalized.get("skill", "")),
                    normalized.get("arguments", {}),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_selfplay":
                value = broker.execute(
                    self.registry.plan(
                        "selfplay.run",
                        {
                            "output_root": normalized.get(
                                "output_root",
                                ".ggen-create/selfplay",
                            )
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_parity_verify":
                value = broker.execute(
                    self.registry.plan(
                        "parity.verify",
                        {
                            "output_root": normalized.get(
                                "output_root",
                                ".ggen-create/parity",
                            ),
                            "variation_value": normalized.get("variation_value"),
                            "ggen_bin": normalized.get("ggen_bin", "ggen"),
                            "sync_args": normalized.get("sync_args"),
                            "reference_dir": normalized.get("reference_dir"),
                            "reference_id": normalized.get("reference_id"),
                            "force": bool(normalized.get("force", True)),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            else:
                raise GgenCreateError("UNKNOWN_TOOL_REFUSED", name)
            return tool_success(value)
        except GgenCreateError as exc:
            return tool_refusal(exc)
        except Exception as exc:
            return tool_internal_error(exc)

    def read_resource(self, uri: str) -> str:
        if uri == "ggen-create://skills":
            value = self.registry.list()
        elif uri == "ggen-create://agents":
            value = self.agents.list()
        elif uri == "ggen-create://receipts/latest":
            value = ReceiptStore(self.root).latest()
            if value is None:
                raise GgenCreateError("RECEIPT_NOT_FOUND_REFUSED", uri)
        elif uri == "ggen-create://receipts/chain":
            value = ReceiptStore(self.root).verify_chain()
        elif uri == "ggen-create://doctor":
            from .doctor import doctor_report

            value = doctor_report(self.root)
        elif uri == "ggen-create://session":
            session_path = find_session(self.root, SESSION_FILE)
            value = Broker(self.root).execute(
                self.registry.plan("capture.inspect", {}),
                session_path=session_path,
            )
        else:
            raise GgenCreateError("RESOURCE_NOT_FOUND_REFUSED", uri)
        return json.dumps(value, indent=2, sort_keys=True, default=str)

    def render_prompt(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "create-factory":
            goal = arguments.get("goal")
            if not isinstance(goal, str) or not goal.strip():
                raise GgenCreateError(
                    "PROMPT_ARGUMENTS_REFUSED",
                    "goal is required",
                )
            return (
                f"Goal: {goal}. Inspect and plan first. Request explicit "
                "confirmation before any native actuation."
            )
        if name == "repair-factory":
            symptom = arguments.get("symptom")
            if not isinstance(symptom, str) or not symptom.strip():
                raise GgenCreateError(
                    "PROMPT_ARGUMENTS_REFUSED",
                    "symptom is required",
                )
            return (
                f"Symptom: {symptom}. Diagnose package integrity and exemplar "
                "drift, then run a bounded confirmed autonomic loop."
            )
        if name == "certify-factory":
            return (
                "Run doctor, package integrity, and receipt-chain verification. "
                "State the narrowest defensible standing; UNKNOWN is not ALIVE."
            )
        raise GgenCreateError("PROMPT_NOT_FOUND_REFUSED", name)
