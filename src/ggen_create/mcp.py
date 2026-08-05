from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
from typing import Any

from .agents import AgentRuntime
from .model import GgenCreateError, SESSION_FILE
from .runtime import ReceiptStore, TaskStore
from .session import find_session
from .skills import Broker, SkillRegistry

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "ggen-create-mcp"
SERVER_VERSION = "0.4.0"
_RELATED_TASK = "io.modelcontextprotocol/related-task"


def _schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _tool(
    name: str,
    title: str,
    description: str,
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    read_only: bool,
    task_support: str = "forbidden",
) -> dict[str, Any]:
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
_CONFIRM = {
    "confirm": {
        "type": "boolean",
        "description": "Explicit bounded actuation authorization.",
    }
}
TOOLS: tuple[dict[str, Any], ...] = (
    _tool(
        "ggen_create_status",
        "Inspect capture",
        "Read correspondence state. Writes nothing.",
        _PROJECT,
        read_only=True,
    ),
    _tool(
        "ggen_create_automatic_plan",
        "Plan automatic creation",
        "Plan package manufacture without writing.",
        {
            **_PROJECT,
            "output_root": {"type": "string", "default": "_ggen"},
            "verify": {"type": "boolean", "default": False},
            "variation_value": {"type": ["string", "null"]},
        },
        read_only=True,
    ),
    _tool(
        "ggen_create_apply",
        "Apply automatic creation",
        "Manufacture a ggen package. Requires confirm:true.",
        {
            **_PROJECT,
            **_CONFIRM,
            "output_root": {"type": "string", "default": "_ggen"},
            "verify": {"type": "boolean", "default": False},
            "variation_value": {"type": ["string", "null"]},
            "ggen_bin": {"type": "string", "default": "ggen"},
            "force": {"type": "boolean", "default": False},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    _tool(
        "ggen_create_autonomic_run",
        "Run autonomic loop",
        "Run bounded MAPE-K convergence. Requires confirm:true.",
        {
            **_PROJECT,
            **_CONFIRM,
            "output_root": {"type": "string", "default": "_ggen"},
            "max_cycles": {"type": "integer", "minimum": 1, "maximum": 100},
            "stable_cycles": {"type": "integer", "minimum": 1, "maximum": 100},
            "verify": {"type": "boolean", "default": False},
            "variation_value": {"type": ["string", "null"]},
            "ggen_bin": {"type": "string", "default": "ggen"},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    _tool(
        "ggen_create_agent_route",
        "Route goal",
        "Route a goal to one bounded agent and skill.",
        {"goal": {"type": "string", "minLength": 1}, "context": {"type": "object"}},
        required=["goal"],
        read_only=True,
    ),
    _tool(
        "ggen_create_agent_dispatch",
        "Dispatch agent",
        "Submit an authorized skill intent through the Broker.",
        {
            **_PROJECT,
            **_CONFIRM,
            "agent": {"type": "string", "minLength": 1},
            "skill": {"type": "string", "minLength": 1},
            "arguments": {"type": "object"},
        },
        required=["agent", "skill", "confirm"],
        read_only=False,
        task_support="optional",
    ),
    _tool(
        "ggen_create_selfplay",
        "Run self-play",
        "Run bounded authority and convergence scenarios.",
        {
            **_PROJECT,
            **_CONFIRM,
            "output_root": {"type": "string", "default": ".ggen-create/selfplay"},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    _tool(
        "ggen_create_parity_verify",
        "Run parity verification",
        "Execute real ggen reconstruction and variation.",
        {
            **_PROJECT,
            **_CONFIRM,
            "output_root": {"type": "string", "default": ".ggen-create/parity"},
            "variation_value": {"type": "string", "minLength": 1},
            "ggen_bin": {"type": "string", "default": "ggen"},
            "sync_args": {"type": "array", "items": {"type": "string"}},
            "reference_dir": {"type": ["string", "null"]},
            "reference_id": {"type": ["string", "null"]},
        },
        required=["confirm", "variation_value"],
        read_only=False,
        task_support="optional",
    ),
    _tool(
        "ggen_create_receipt_verify",
        "Verify receipt",
        "Verify the latest or named native receipt.",
        {**_PROJECT, "path": {"type": ["string", "null"]}},
        read_only=True,
    ),
)
_TOOL_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        value["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": value}


def _tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    structured = value if isinstance(value, dict) else {"value": value}
    return {
        "content": [
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
        "structuredContent": structured,
        "isError": is_error,
    }


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "taskId",
        "status",
        "statusMessage",
        "createdAt",
        "lastUpdatedAt",
        "ttl",
        "pollInterval",
    )
    return {key: task[key] for key in keys if task.get(key) is not None}


def _related(task_id: str) -> dict[str, Any]:
    return {_RELATED_TASK: {"taskId": task_id}}


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if expected is not None:
        alternatives = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_matches(value, item) for item in alternatives):
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} must have type {alternatives}",
            )
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        missing = [name for name in required if name not in value]
        if missing:
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} missing required properties: {missing}",
            )
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise GgenCreateError(
                    "TOOL_ARGUMENT_SCHEMA_REFUSED",
                    f"{path} has unsupported properties: {extras}",
                )
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _validate_schema(child, child_schema, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            _validate_schema(child, schema["items"], f"{path}[{index}]")
    if isinstance(value, str) and "minLength" in schema:
        if len(value) < int(schema["minLength"]):
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} is shorter than minLength",
            )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} is below minimum",
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} is above maximum",
            )


class McpServer:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.negotiated = False
        self.ready = False
        self.client_capabilities: dict[str, Any] = {}
        self.tasks_enabled = False
        self.registry = SkillRegistry()
        self.agents = AgentRuntime(self.root)
        self.tasks = TaskStore(self.root, "mcp")

    def _session(self, arguments: dict[str, Any]) -> Path:
        project = str(arguments.get("project", SESSION_FILE))
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError(
                "PROJECT_NAME_REFUSED",
                "project must be a capture filename",
            )
        return find_session(self.root, project)

    def _require_ready(self) -> None:
        if not self.ready:
            raise GgenCreateError(
                "MCP_LIFECYCLE_REFUSED",
                "initialize and notifications/initialized are required",
            )

    def _require_tasks(self) -> None:
        if not self.tasks_enabled:
            raise GgenCreateError(
                "MCP_TASKS_NOT_NEGOTIATED_REFUSED",
                "client did not advertise task capability",
            )

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        try:
            if request.get("jsonrpc") != "2.0" or not isinstance(
                request.get("method"), str
            ):
                return _error(request_id, -32600, "Invalid Request")
            method = request["method"]
            params = request.get("params") or {}
            if not isinstance(params, dict):
                return _error(request_id, -32602, "Invalid params")

            if method == "initialize":
                requested = params.get("protocolVersion")
                if requested != MCP_PROTOCOL_VERSION:
                    return _error(
                        request_id,
                        -32602,
                        "Unsupported protocol version",
                        {
                            "requested": requested,
                            "supported": MCP_PROTOCOL_VERSION,
                        },
                    )
                capabilities = params.get("capabilities") or {}
                if not isinstance(capabilities, dict):
                    return _error(request_id, -32602, "Invalid capabilities")
                self.client_capabilities = capabilities
                self.tasks_enabled = isinstance(capabilities.get("tasks"), dict)
                self.negotiated = True
                self.ready = False
                return _result(
                    request_id,
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {
                                "subscribe": False,
                                "listChanged": False,
                            },
                            "prompts": {"listChanged": False},
                            "tasks": {
                                "list": {},
                                "cancel": {},
                                "requests": {"tools": {"call": {}}},
                            },
                        },
                        "serverInfo": {
                            "name": SERVER_NAME,
                            "title": "ggen-create MCP",
                            "version": SERVER_VERSION,
                        },
                        "instructions": (
                            "Inspect and plan first. Every write tool requires "
                            "confirm:true. The Broker is the only DO boundary."
                        ),
                    },
                )

            if method == "notifications/initialized":
                if not self.negotiated:
                    raise GgenCreateError(
                        "MCP_LIFECYCLE_REFUSED",
                        "initialized notification preceded initialize",
                    )
                self.ready = True
                return None

            if method == "notifications/cancelled":
                return None
            if method == "ping":
                return _result(request_id, {})

            self._require_ready()

            if method == "tools/list":
                return _result(
                    request_id,
                    {"tools": list(TOOLS), "nextCursor": None},
                )
            if method == "tools/call":
                return _result(request_id, self._call_tool(params))
            if method == "resources/list":
                return _result(
                    request_id,
                    {"resources": self._resources(), "nextCursor": None},
                )
            if method == "resources/read":
                return _result(
                    request_id,
                    self._read_resource(str(params.get("uri", ""))),
                )
            if method == "prompts/list":
                return _result(
                    request_id,
                    {"prompts": self._prompts(), "nextCursor": None},
                )
            if method == "prompts/get":
                return _result(
                    request_id,
                    self._prompt(
                        str(params.get("name", "")),
                        params.get("arguments") or {},
                    ),
                )

            if method.startswith("tasks/"):
                self._require_tasks()
            if method == "tasks/get":
                return _result(
                    request_id,
                    _public_task(
                        self.tasks.get(str(params.get("taskId", "")))
                    ),
                )
            if method == "tasks/list":
                page = self.tasks.query(
                    status=params.get("status"),
                    cursor=params.get("cursor"),
                    page_size=int(params.get("pageSize", 50)),
                )
                return _result(
                    request_id,
                    {
                        "tasks": [
                            _public_task(task) for task in page["tasks"]
                        ],
                        "nextCursor": page["nextCursor"],
                        "totalSize": page["totalSize"],
                    },
                )
            if method == "tasks/result":
                return self._task_result(
                    request_id,
                    str(params.get("taskId", "")),
                )
            if method == "tasks/cancel":
                return _result(
                    request_id,
                    _public_task(
                        self.tasks.cancel(str(params.get("taskId", "")))
                    ),
                )
            return _error(request_id, -32601, f"Method not found: {method}")
        except GgenCreateError as exc:
            code = {
                "TASK_NOT_FOUND_REFUSED": -32001,
                "TASK_NOT_CANCELABLE_REFUSED": -32002,
                "TASK_EXPIRED_REFUSED": -32003,
                "MCP_TASKS_NOT_NEGOTIATED_REFUSED": -32601,
                "MCP_LIFECYCLE_REFUSED": -32002,
            }.get(exc.code, -32602)
            return _error(request_id, code, exc.code, {"detail": exc.detail})
        except Exception as exc:  # protocol containment
            return _error(
                request_id,
                -32603,
                "Internal error",
                {"type": type(exc).__name__, "detail": str(exc)},
            )

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in _TOOL_BY_NAME:
            return _tool_result(
                {"code": "UNKNOWN_TOOL_REFUSED", "detail": str(name)},
                is_error=True,
            )
        if not isinstance(arguments, dict):
            return _tool_result(
                {
                    "code": "TOOL_ARGUMENTS_REFUSED",
                    "detail": "arguments must be an object",
                },
                is_error=True,
            )
        try:
            _validate_schema(arguments, _TOOL_BY_NAME[name]["inputSchema"])
        except GgenCreateError as exc:
            return _tool_result(
                {"code": exc.code, "detail": exc.detail},
                is_error=True,
            )

        task_request = params.get("task")
        if task_request is None:
            return self._execute(name, arguments)

        self._require_tasks()
        if _TOOL_BY_NAME[name]["execution"]["taskSupport"] == "forbidden":
            raise GgenCreateError("MCP_TASK_UNSUPPORTED_REFUSED", name)
        if not isinstance(task_request, dict):
            raise GgenCreateError(
                "MCP_TASK_REQUEST_REFUSED",
                "task must be an object",
            )
        ttl_raw = task_request.get("ttl", 300_000)
        ttl = None if ttl_raw is None else int(ttl_raw)
        task = self.tasks.create(
            kind="tools/call",
            request={"name": name, "arguments": arguments},
            ttl=ttl,
            poll_interval=int(task_request.get("pollInterval", 250)),
        )
        worker = threading.Thread(
            target=self._run_task,
            args=(task["taskId"], name, arguments),
            name=f"ggen-create-mcp-{task['taskId']}",
            daemon=True,
        )
        worker.start()
        return {"task": _public_task(task)}

    def _run_task(
        self,
        task_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        value = self._execute(name, arguments)
        try:
            current = self.tasks.get(task_id)
            if current["status"] != "working":
                return
            if value["isError"]:
                self.tasks.fail(
                    task_id,
                    {
                        "rpcCode": -32602,
                        "message": "Tool execution failed",
                        "data": value["structuredContent"],
                    },
                )
            else:
                self.tasks.complete(task_id, value)
        except GgenCreateError as exc:
            if exc.code not in {
                "TASK_TRANSITION_REFUSED",
                "TASK_NOT_FOUND_REFUSED",
                "TASK_EXPIRED_REFUSED",
            }:
                try:
                    self.tasks.fail(
                        task_id,
                        {
                            "rpcCode": -32603,
                            "message": exc.code,
                            "data": {"detail": exc.detail},
                        },
                    )
                except GgenCreateError:
                    pass

    def _task_result(
        self,
        request_id: Any,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        metadata = _related(task_id)
        if task["status"] == "completed":
            value = task["result"]
            if isinstance(value, dict):
                value = dict(value)
                value["_meta"] = metadata
            else:
                value = {"value": value, "_meta": metadata}
            return _result(request_id, value)
        if task["status"] in self.tasks.INTERRUPTED:
            return _result(
                request_id,
                {
                    "request": task["result"],
                    "_meta": metadata,
                },
            )
        if task["status"] in {"failed", "rejected"}:
            error = task.get("error") or {}
            return _error(
                request_id,
                int(error.get("rpcCode", -32603)),
                str(error.get("message", "Task failed")),
                {
                    **(error.get("data") or {}),
                    "_meta": metadata,
                },
            )
        if task["status"] == "cancelled":
            return _error(
                request_id,
                -32002,
                "Task cancelled",
                {"_meta": metadata},
            )
        return _error(
            request_id,
            -32000,
            "Task not ready",
            {
                "status": task["status"],
                "pollInterval": task.get("pollInterval"),
                "_meta": metadata,
            },
        )

    def _execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            session = self._session(arguments)
            broker = Broker(self.root)
            confirm = bool(arguments.get("confirm", False))
            if name == "ggen_create_status":
                value = broker.execute(
                    self.registry.plan("capture.inspect", {}),
                    session_path=session,
                )
            elif name == "ggen_create_automatic_plan":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.plan",
                        {
                            "output_root": arguments.get(
                                "output_root", "_ggen"
                            ),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get(
                                "variation_value"
                            ),
                        },
                    ),
                    session_path=session,
                )
            elif name == "ggen_create_apply":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.create",
                        {
                            "output_root": arguments.get(
                                "output_root", "_ggen"
                            ),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get(
                                "variation_value"
                            ),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                            "force": bool(arguments.get("force", False)),
                        },
                    ),
                    session_path=session,
                    confirm=confirm,
                )
            elif name == "ggen_create_autonomic_run":
                value = broker.execute(
                    self.registry.plan(
                        "autonomic.run",
                        {
                            "output_root": arguments.get(
                                "output_root", "_ggen"
                            ),
                            "max_cycles": int(
                                arguments.get("max_cycles", 4)
                            ),
                            "stable_cycles": int(
                                arguments.get("stable_cycles", 2)
                            ),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get(
                                "variation_value"
                            ),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                        },
                    ),
                    session_path=session,
                    confirm=confirm,
                )
            elif name == "ggen_create_agent_route":
                value = self.agents.route(
                    str(arguments.get("goal", "")),
                    arguments.get("context", {}),
                )
            elif name == "ggen_create_agent_dispatch":
                value = self.agents.dispatch(
                    str(arguments.get("agent", "")),
                    str(arguments.get("skill", "")),
                    arguments.get("arguments", {}),
                    session_path=session,
                    confirm=confirm,
                )
            elif name == "ggen_create_selfplay":
                value = broker.execute(
                    self.registry.plan(
                        "selfplay.run",
                        {
                            "output_root": arguments.get(
                                "output_root", ".ggen-create/selfplay"
                            )
                        },
                    ),
                    session_path=session,
                    confirm=confirm,
                )
            elif name == "ggen_create_parity_verify":
                value = broker.execute(
                    self.registry.plan(
                        "parity.verify",
                        {
                            "output_root": arguments.get(
                                "output_root", ".ggen-create/parity"
                            ),
                            "variation_value": arguments.get(
                                "variation_value"
                            ),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                            "sync_args": arguments.get("sync_args"),
                            "reference_dir": arguments.get("reference_dir"),
                            "reference_id": arguments.get("reference_id"),
                        },
                    ),
                    session_path=session,
                    confirm=confirm,
                )
            elif name == "ggen_create_receipt_verify":
                value = broker.execute(
                    self.registry.plan(
                        "receipt.verify",
                        {"path": arguments.get("path")},
                    ),
                    session_path=session,
                )
            else:
                raise GgenCreateError("UNKNOWN_TOOL_REFUSED", name)
            return _tool_result(value)
        except GgenCreateError as exc:
            return _tool_result(
                {"code": exc.code, "detail": exc.detail},
                is_error=True,
            )

    @staticmethod
    def _resources() -> list[dict[str, Any]]:
        return [
            {
                "uri": "ggen-create://session",
                "name": "capture-session",
                "title": "Active capture",
                "mimeType": "application/json",
            },
            {
                "uri": "ggen-create://skills",
                "name": "skills",
                "title": "Create-time skills",
                "mimeType": "application/json",
            },
            {
                "uri": "ggen-create://agents",
                "name": "agents",
                "title": "Bounded agents",
                "mimeType": "application/json",
            },
            {
                "uri": "ggen-create://receipts/latest",
                "name": "latest-receipt",
                "title": "Latest receipt",
                "mimeType": "application/json",
            },
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
            value = Broker(self.root).execute(
                self.registry.plan("capture.inspect", {}),
                session_path=session,
            )
        else:
            raise GgenCreateError("RESOURCE_NOT_FOUND_REFUSED", uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(
                        value,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    ),
                }
            ]
        }

    @staticmethod
    def _prompts() -> list[dict[str, Any]]:
        return [
            {
                "name": "create-factory",
                "title": "Create an admitted factory",
                "description": "Inspect, plan, apply, verify, receipt.",
                "arguments": [{"name": "goal", "required": True}],
            },
            {
                "name": "repair-factory",
                "title": "Repair a drifting factory",
                "description": "Use bounded autonomic convergence.",
                "arguments": [{"name": "symptom", "required": True}],
            },
            {
                "name": "certify-factory",
                "title": "Calculate standing",
                "description": (
                    "Verify receipts and refuse unsupported claims."
                ),
                "arguments": [],
            },
        ]

    @staticmethod
    def _prompt(
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise GgenCreateError(
                "PROMPT_ARGUMENTS_REFUSED",
                "arguments must be an object",
            )
        if name == "create-factory":
            goal = arguments.get("goal")
            if not isinstance(goal, str) or not goal.strip():
                raise GgenCreateError(
                    "PROMPT_ARGUMENTS_REFUSED",
                    "goal is required",
                )
            text = (
                f"Goal: {goal}. Inspect, plan, then request explicit "
                "confirmation before apply."
            )
        elif name == "repair-factory":
            symptom = arguments.get("symptom")
            if not isinstance(symptom, str) or not symptom.strip():
                raise GgenCreateError(
                    "PROMPT_ARGUMENTS_REFUSED",
                    "symptom is required",
                )
            text = (
                f"Symptom: {symptom}. Diagnose and run a bounded autonomic "
                "loop only after confirmation."
            )
        elif name == "certify-factory":
            text = (
                "Verify receipts and state the narrowest defensible standing. "
                "UNKNOWN is not ALIVE."
            )
        else:
            raise GgenCreateError("PROMPT_NOT_FOUND_REFUSED", name)
        return {
            "description": name,
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": text},
                }
            ],
        }


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
            sys.stdout.write(
                json.dumps(response, separators=(",", ":"), default=str)
                + "\n"
            )
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-mcp")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    raise SystemExit(stdio_main(Path(args.root)))


if __name__ == "__main__":
    main()
