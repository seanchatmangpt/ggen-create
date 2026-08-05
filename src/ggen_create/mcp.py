from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .agents import AgentRuntime
from .model import GgenCreateError, SESSION_FILE
from .runtime import ReceiptStore, TaskStore
from .session import find_session
from .skills import Broker, SkillRegistry

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "ggen-create-mcp"


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _tool(name: str, title: str, description: str, properties: dict[str, Any], *, required: list[str] | None = None, read_only: bool, task_support: str = "forbidden") -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": _schema(properties, required),
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "title": title,
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "idempotentHint": read_only,
            "openWorldHint": False,
        },
        "execution": {"taskSupport": task_support},
    }


_PROJECT = {"project": {"type": "string", "default": SESSION_FILE}}
_CONFIRM = {"confirm": {"type": "boolean", "description": "Explicit bounded actuation authorization."}}
TOOLS: tuple[dict[str, Any], ...] = (
    _tool("ggen_create_status", "Inspect capture", "Read correspondence state. Writes nothing.", _PROJECT, read_only=True),
    _tool("ggen_create_automatic_plan", "Plan automatic creation", "Plan package manufacture without writing.", {**_PROJECT, "output_root": {"type": "string", "default": "_ggen"}, "verify": {"type": "boolean", "default": False}, "variation_value": {"type": ["string", "null"]}}, read_only=True),
    _tool("ggen_create_apply", "Apply automatic creation", "Manufacture a ggen package. Requires confirm:true.", {**_PROJECT, **_CONFIRM, "output_root": {"type": "string", "default": "_ggen"}, "verify": {"type": "boolean", "default": False}, "variation_value": {"type": ["string", "null"]}, "ggen_bin": {"type": "string", "default": "ggen"}, "force": {"type": "boolean", "default": False}}, required=["confirm"], read_only=False, task_support="optional"),
    _tool("ggen_create_autonomic_run", "Run autonomic loop", "Run bounded MAPE-K convergence. Requires confirm:true.", {**_PROJECT, **_CONFIRM, "output_root": {"type": "string", "default": "_ggen"}, "max_cycles": {"type": "integer", "minimum": 1, "maximum": 100}, "stable_cycles": {"type": "integer", "minimum": 1, "maximum": 100}, "verify": {"type": "boolean", "default": False}, "variation_value": {"type": ["string", "null"]}, "ggen_bin": {"type": "string", "default": "ggen"}}, required=["confirm"], read_only=False, task_support="optional"),
    _tool("ggen_create_agent_route", "Route goal", "Route a goal to one bounded agent and skill.", {"goal": {"type": "string", "minLength": 1}, "context": {"type": "object"}}, required=["goal"], read_only=True),
    _tool("ggen_create_agent_dispatch", "Dispatch agent", "Submit an authorized skill intent through the Broker.", {**_PROJECT, **_CONFIRM, "agent": {"type": "string"}, "skill": {"type": "string"}, "arguments": {"type": "object"}}, required=["agent", "skill"], read_only=False, task_support="optional"),
    _tool("ggen_create_selfplay", "Run self-play", "Run bounded authority and convergence scenarios.", {**_PROJECT, **_CONFIRM, "output_root": {"type": "string", "default": ".ggen-create/selfplay"}}, required=["confirm"], read_only=False, task_support="optional"),
    _tool("ggen_create_parity_verify", "Run parity verification", "Execute real ggen reconstruction and variation.", {**_PROJECT, **_CONFIRM, "output_root": {"type": "string", "default": ".ggen-create/parity"}, "variation_value": {"type": "string", "minLength": 1}, "ggen_bin": {"type": "string", "default": "ggen"}, "sync_args": {"type": "array", "items": {"type": "string"}}, "reference_dir": {"type": ["string", "null"]}, "reference_id": {"type": ["string", "null"]}}, required=["confirm", "variation_value"], read_only=False, task_support="optional"),
    _tool("ggen_create_receipt_verify", "Verify receipt", "Verify the latest or named native receipt.", {**_PROJECT, "path": {"type": ["string", "null"]}}, read_only=True),
)
_TOOL_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    value: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        value["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": value}


def _tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    structured = value if isinstance(value, dict) else {"value": value}
    return {
        "content": [{"type": "text", "text": json.dumps(structured, indent=2, sort_keys=True, default=str)}],
        "structuredContent": structured,
        "isError": is_error,
    }


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: task[key] for key in ("taskId", "status", "statusMessage", "createdAt", "lastUpdatedAt", "ttl", "pollInterval") if task.get(key) is not None}


class McpServer:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.initialized = False
        self.registry = SkillRegistry()
        self.agents = AgentRuntime(self.root)
        self.tasks = TaskStore(self.root, "mcp")

    def _session(self, arguments: dict[str, Any]) -> Path:
        project = str(arguments.get("project", SESSION_FILE))
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError("PROJECT_NAME_REFUSED", "project must be a capture filename")
        return find_session(self.root, project)

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        try:
            if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                return _error(request_id, -32600, "Invalid Request")
            method = request["method"]
            params = request.get("params") or {}
            if not isinstance(params, dict):
                return _error(request_id, -32602, "Invalid params")
            if method in {"notifications/initialized", "notifications/cancelled"}:
                return None
            if method == "initialize":
                self.initialized = True
                return _result(request_id, {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                        "tasks": {"list": {}, "cancel": {}, "requests": {"tools": {"call": {}}}},
                    },
                    "serverInfo": {"name": SERVER_NAME, "title": "ggen-create MCP", "version": "0.3.0"},
                    "instructions": "Inspect and plan first. Every write tool requires confirm:true. The Broker is the only DO boundary.",
                })
            if method == "ping":
                return _result(request_id, {})
            if not self.initialized:
                return _error(request_id, -32002, "Server not initialized")
            if method == "tools/list":
                return _result(request_id, {"tools": list(TOOLS), "nextCursor": None})
            if method == "tools/call":
                return _result(request_id, self._call_tool(params))
            if method == "resources/list":
                return _result(request_id, {"resources": self._resources(), "nextCursor": None})
            if method == "resources/read":
                return _result(request_id, self._read_resource(str(params.get("uri", ""))))
            if method == "prompts/list":
                return _result(request_id, {"prompts": self._prompts(), "nextCursor": None})
            if method == "prompts/get":
                return _result(request_id, self._prompt(str(params.get("name", "")), params.get("arguments") or {}))
            if method == "tasks/get":
                return _result(request_id, _public_task(self.tasks.get(str(params.get("taskId", "")))))
            if method == "tasks/list":
                return _result(request_id, {"tasks": [_public_task(task) for task in self.tasks.list()], "nextCursor": None})
            if method == "tasks/result":
                return _result(request_id, self.tasks.result(str(params.get("taskId", ""))))
            if method == "tasks/cancel":
                return _result(request_id, _public_task(self.tasks.cancel(str(params.get("taskId", "")))))
            return _error(request_id, -32601, f"Method not found: {method}")
        except GgenCreateError as exc:
            return _error(request_id, -32602, exc.code, {"detail": exc.detail})
        except Exception as exc:  # protocol containment
            return _error(request_id, -32603, "Internal error", {"type": type(exc).__name__, "detail": str(exc)})

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in _TOOL_BY_NAME:
            return _tool_result({"code": "UNKNOWN_TOOL_REFUSED", "detail": str(name)}, is_error=True)
        if not isinstance(arguments, dict):
            return _tool_result({"code": "TOOL_ARGUMENTS_REFUSED", "detail": "arguments must be an object"}, is_error=True)
        task_request = params.get("task")
        if task_request is not None:
            if _TOOL_BY_NAME[name]["execution"]["taskSupport"] == "forbidden":
                return _tool_result({"code": "TASK_UNSUPPORTED", "detail": name}, is_error=True)
            ttl = int(task_request.get("ttl", 300000)) if isinstance(task_request, dict) else 300000
            task = self.tasks.create(kind="tools/call", request={"name": name, "arguments": arguments}, ttl=ttl)
            value = self._execute(name, arguments)
            if value["isError"]:
                self.tasks.fail(task["taskId"], value)
            else:
                self.tasks.complete(task["taskId"], value)
            return {"task": _public_task(self.tasks.get(task["taskId"]))}
        return self._execute(name, arguments)

    def _execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            session = self._session(arguments)
            broker = Broker(self.root)
            confirm = bool(arguments.get("confirm", False))
            if name == "ggen_create_status":
                value = broker.execute(self.registry.plan("capture.inspect", {}), session_path=session)
            elif name == "ggen_create_automatic_plan":
                value = broker.execute(self.registry.plan("automatic.plan", {"output_root": arguments.get("output_root", "_ggen"), "verify": bool(arguments.get("verify", False)), "variation_value": arguments.get("variation_value")}), session_path=session)
            elif name == "ggen_create_apply":
                value = broker.execute(self.registry.plan("automatic.create", {"output_root": arguments.get("output_root", "_ggen"), "verify": bool(arguments.get("verify", False)), "variation_value": arguments.get("variation_value"), "ggen_bin": arguments.get("ggen_bin", "ggen"), "force": bool(arguments.get("force", False))}), session_path=session, confirm=confirm)
            elif name == "ggen_create_autonomic_run":
                value = broker.execute(self.registry.plan("autonomic.run", {"output_root": arguments.get("output_root", "_ggen"), "max_cycles": int(arguments.get("max_cycles", 4)), "stable_cycles": int(arguments.get("stable_cycles", 2)), "verify": bool(arguments.get("verify", False)), "variation_value": arguments.get("variation_value"), "ggen_bin": arguments.get("ggen_bin", "ggen")}), session_path=session, confirm=confirm)
            elif name == "ggen_create_agent_route":
                value = self.agents.route(str(arguments.get("goal", "")), arguments.get("context", {}))
            elif name == "ggen_create_agent_dispatch":
                value = self.agents.dispatch(str(arguments.get("agent", "")), str(arguments.get("skill", "")), arguments.get("arguments", {}), session_path=session, confirm=confirm)
            elif name == "ggen_create_selfplay":
                value = broker.execute(self.registry.plan("selfplay.run", {"output_root": arguments.get("output_root", ".ggen-create/selfplay")}), session_path=session, confirm=confirm)
            elif name == "ggen_create_parity_verify":
                value = broker.execute(self.registry.plan("parity.verify", {"output_root": arguments.get("output_root", ".ggen-create/parity"), "variation_value": arguments.get("variation_value"), "ggen_bin": arguments.get("ggen_bin", "ggen"), "sync_args": arguments.get("sync_args"), "reference_dir": arguments.get("reference_dir"), "reference_id": arguments.get("reference_id")}), session_path=session, confirm=confirm)
            elif name == "ggen_create_receipt_verify":
                value = broker.execute(self.registry.plan("receipt.verify", {"path": arguments.get("path")}), session_path=session)
            else:
                raise GgenCreateError("UNKNOWN_TOOL_REFUSED", name)
            return _tool_result(value)
        except GgenCreateError as exc:
            return _tool_result({"code": exc.code, "detail": exc.detail}, is_error=True)

    @staticmethod
    def _resources() -> list[dict[str, Any]]:
        return [
            {"uri": "ggen-create://session", "name": "capture-session", "title": "Active capture", "mimeType": "application/json"},
            {"uri": "ggen-create://skills", "name": "skills", "title": "Create-time skills", "mimeType": "application/json"},
            {"uri": "ggen-create://agents", "name": "agents", "title": "Bounded agents", "mimeType": "application/json"},
            {"uri": "ggen-create://receipts/latest", "name": "latest-receipt", "title": "Latest receipt", "mimeType": "application/json"},
        ]

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "ggen-create://skills":
            value = self.registry.list()
        elif uri == "ggen-create://agents":
            value = self.agents.list()
        elif uri == "ggen-create://receipts/latest":
            value = ReceiptStore(self.root).latest()
            if value is None:
                raise GgenCreateError("RECEIPT_NOT_FOUND_REFUSED", uri)
        elif uri == "ggen-create://session":
            session = find_session(self.root, SESSION_FILE)
            value = Broker(self.root).execute(self.registry.plan("capture.inspect", {}), session_path=session)
        else:
            raise GgenCreateError("RESOURCE_NOT_FOUND_REFUSED", uri)
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(value, indent=2, sort_keys=True, default=str)}]}

    @staticmethod
    def _prompts() -> list[dict[str, Any]]:
        return [
            {"name": "create-factory", "title": "Create an admitted factory", "description": "Inspect, plan, apply, verify, receipt.", "arguments": [{"name": "goal", "required": True}]},
            {"name": "repair-factory", "title": "Repair a drifting factory", "description": "Use bounded autonomic convergence.", "arguments": [{"name": "symptom", "required": True}]},
            {"name": "certify-factory", "title": "Calculate standing", "description": "Verify receipts and refuse unsupported claims.", "arguments": []},
        ]

    @staticmethod
    def _prompt(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "create-factory":
            text = f"Goal: {arguments.get('goal', '')}. Inspect, plan, then request explicit confirmation before apply."
        elif name == "repair-factory":
            text = f"Symptom: {arguments.get('symptom', '')}. Diagnose and run a bounded autonomic loop only after confirmation."
        elif name == "certify-factory":
            text = "Verify receipts and state the narrowest defensible standing. UNKNOWN is not ALIVE."
        else:
            raise GgenCreateError("PROMPT_NOT_FOUND_REFUSED", name)
        return {"description": name, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


def stdio_main(root: Path | None = None) -> int:
    server = McpServer(root or Path.cwd())
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, "Parse error", str(exc))
        else:
            response = server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), default=str) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-mcp")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    raise SystemExit(stdio_main(Path(args.root)))


if __name__ == "__main__":
    main()
