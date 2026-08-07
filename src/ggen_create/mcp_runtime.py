from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
from typing import Any

from .agents import AgentRuntime
from .model import APP_VERSION, GgenCreateError, SESSION_FILE
from .runtime import ReceiptStore, TaskStore
from .session import find_session
from .skills import Broker, SkillRegistry

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "ggen-create-mcp"
SERVER_VERSION = APP_VERSION
RELATED_TASK_KEY = "io.modelcontextprotocol/related-task"


def object_schema(
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


def tool(
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
        "inputSchema": object_schema(properties, required),
        "outputSchema": {
            "type": "object",
            "additionalProperties": True,
        },
        "annotations": {
            "title": title,
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "idempotentHint": read_only,
            "openWorldHint": False,
        },
        "execution": {"taskSupport": task_support},
    }


PROJECT = {
    "project": {
        "type": "string",
        "default": SESSION_FILE,
    }
}
CONFIRM = {
    "confirm": {
        "type": "boolean",
        "description": "Explicit bounded actuation authorization.",
    }
}
OUTPUT = {
    "output_root": {
        "type": "string",
        "default": "_ggen",
    }
}
VERIFY = {
    "verify": {"type": "boolean", "default": False},
    "variation_value": {"type": ["string", "null"]},
    "ggen_bin": {"type": "string", "default": "ggen"},
}

TOOLS: tuple[dict[str, Any], ...] = (
    tool(
        "ggen_create_status",
        "Inspect capture",
        "Read admitted correspondence state.",
        PROJECT,
        read_only=True,
    ),
    tool(
        "ggen_create_automatic_plan",
        "Plan automatic creation",
        "Plan package manufacture without writing.",
        {**PROJECT, **OUTPUT, **VERIFY},
        read_only=True,
    ),
    tool(
        "ggen_create_package_verify",
        "Verify package integrity",
        "Compare a package byte-for-byte with its package receipt.",
        {
            **PROJECT,
            **OUTPUT,
            "package": {"type": ["string", "null"]},
        },
        read_only=True,
    ),
    tool(
        "ggen_create_apply",
        "Apply automatic creation",
        "Manufacture a deterministic ggen package.",
        {
            **PROJECT,
            **CONFIRM,
            **OUTPUT,
            **VERIFY,
            "force": {"type": "boolean", "default": False},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_automatic_watch",
        "Watch and reconcile",
        "Observe bounded fingerprint and package-integrity drift.",
        {
            **PROJECT,
            **CONFIRM,
            **OUTPUT,
            **VERIFY,
            "cycles": {"type": "integer", "minimum": 1, "maximum": 100},
            "interval_seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 3600,
            },
            "force": {"type": "boolean", "default": False},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_autonomic_cycle",
        "Run autonomic cycle",
        "Execute one bounded MAPE-K cycle.",
        {
            **PROJECT,
            **CONFIRM,
            **OUTPUT,
            **VERIFY,
            "apply": {"type": "boolean", "default": True},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_autonomic_run",
        "Run autonomic convergence",
        "Run bounded MAPE-K convergence with a cycle ceiling.",
        {
            **PROJECT,
            **CONFIRM,
            **OUTPUT,
            **VERIFY,
            "max_cycles": {"type": "integer", "minimum": 1, "maximum": 100},
            "stable_cycles": {"type": "integer", "minimum": 1, "maximum": 100},
            "interval_seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 3600,
            },
            "apply": {"type": "boolean", "default": True},
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_agent_route",
        "Route goal",
        "Route a goal deterministically to a bounded agent and skill.",
        {
            "goal": {"type": "string", "minLength": 1},
            "context": {"type": "object"},
        },
        required=["goal"],
        read_only=True,
    ),
    tool(
        "ggen_create_agent_dispatch",
        "Dispatch agent",
        "Submit an authorized skill intent through the Broker.",
        {
            **PROJECT,
            **CONFIRM,
            "agent": {"type": "string", "minLength": 1},
            "skill": {"type": "string", "minLength": 1},
            "arguments": {"type": "object"},
        },
        required=["agent", "skill", "confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_selfplay",
        "Run self-play",
        "Run bounded authority, protocol, integrity, and convergence scenarios.",
        {
            **PROJECT,
            **CONFIRM,
            "output_root": {
                "type": "string",
                "default": ".ggen-create/selfplay",
            },
        },
        required=["confirm"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_parity_verify",
        "Run parity verification",
        "Execute reconstruction, variation, and optional original-reference parity.",
        {
            **PROJECT,
            **CONFIRM,
            "output_root": {
                "type": "string",
                "default": ".ggen-create/parity",
            },
            "variation_value": {"type": "string", "minLength": 1},
            "ggen_bin": {"type": "string", "default": "ggen"},
            "sync_args": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reference_dir": {"type": ["string", "null"]},
            "reference_id": {"type": ["string", "null"]},
            "force": {"type": "boolean", "default": True},
        },
        required=["confirm", "variation_value"],
        read_only=False,
        task_support="optional",
    ),
    tool(
        "ggen_create_receipt_verify",
        "Verify receipt",
        "Recompute the latest or named native receipt digest.",
        {
            **PROJECT,
            "path": {"type": ["string", "null"]},
        },
        read_only=True,
    ),
    tool(
        "ggen_create_receipt_chain_verify",
        "Verify receipt chain",
        "Verify native receipt roots, parents, branches, orphans, and latest pointer.",
        PROJECT,
        read_only=True,
    ),
    tool(
        "ggen_create_doctor",
        "Inspect runtime standing",
        "Calculate evidence-backed runtime, package, ledger, and task standing.",
        PROJECT,
        read_only=True,
    ),
)
TOOL_BY_NAME = {item["name"]: item for item in TOOLS}


def result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": body}


def tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
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


def public_task(task: dict[str, Any]) -> dict[str, Any]:
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


def related_task(task_id: str) -> dict[str, Any]:
    return {RELATED_TASK_KEY: {"taskId": task_id}}


def type_matches(value: Any, expected: str) -> bool:
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


def validate_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    expected = schema.get("type")
    if expected is not None:
        alternatives = [expected] if isinstance(expected, str) else list(expected)
        if not any(type_matches(value, item) for item in alternatives):
            raise GgenCreateError(
                "TOOL_ARGUMENT_SCHEMA_REFUSED",
                f"{path} must have type {alternatives}",
            )
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        missing = [
            name
            for name in schema.get("required") or []
            if name not in value
        ]
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
                validate_schema(child, child_schema, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            validate_schema(child, schema["items"], f"{path}[{index}]")
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

    def session(self, arguments: dict[str, Any]) -> Path:
        project = str(arguments.get("project", SESSION_FILE))
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError(
                "PROJECT_NAME_REFUSED",
                "project must be a capture filename",
            )
        return find_session(self.root, project)

    def require_ready(self) -> None:
        if not self.ready:
            raise GgenCreateError(
                "MCP_LIFECYCLE_REFUSED",
                "initialize and notifications/initialized are required",
            )

    def require_tasks(self) -> None:
        if not self.tasks_enabled:
            raise GgenCreateError(
                "MCP_TASKS_NOT_NEGOTIATED_REFUSED",
                "client did not advertise task capability",
            )

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        is_notification = "id" not in request
        try:
            if request.get("jsonrpc") != "2.0" or not isinstance(
                request.get("method"), str
            ):
                return None if is_notification else error(
                    request_id,
                    -32600,
                    "Invalid Request",
                )
            method = request["method"]
            params = request.get("params") or {}
            if not isinstance(params, dict):
                return None if is_notification else error(
                    request_id,
                    -32602,
                    "Invalid params",
                )

            if method == "initialize":
                requested = params.get("protocolVersion")
                if requested != MCP_PROTOCOL_VERSION:
                    return error(
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
                    return error(request_id, -32602, "Invalid capabilities")
                self.client_capabilities = capabilities
                self.tasks_enabled = isinstance(
                    capabilities.get("tasks"),
                    dict,
                )
                self.negotiated = True
                self.ready = False
                return result(
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
                            "confirm:true. The Broker is the only native DO boundary."
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
                return result(request_id, {})

            self.require_ready()
            if method == "tools/list":
                return result(
                    request_id,
                    {"tools": list(TOOLS), "nextCursor": None},
                )
            if method == "tools/call":
                return result(request_id, self.call_tool(params))
            if method == "resources/list":
                return result(
                    request_id,
                    {"resources": self.resources(), "nextCursor": None},
                )
            if method == "resources/read":
                return result(
                    request_id,
                    self.read_resource(str(params.get("uri", ""))),
                )
            if method == "prompts/list":
                return result(
                    request_id,
                    {"prompts": self.prompts(), "nextCursor": None},
                )
            if method == "prompts/get":
                return result(
                    request_id,
                    self.prompt(
                        str(params.get("name", "")),
                        params.get("arguments") or {},
                    ),
                )

            if method.startswith("tasks/"):
                self.require_tasks()
            if method == "tasks/get":
                return result(
                    request_id,
                    public_task(
                        self.tasks.get(str(params.get("taskId", "")))
                    ),
                )
            if method == "tasks/list":
                page = self.tasks.query(
                    status=params.get("status"),
                    cursor=params.get("cursor"),
                    page_size=int(params.get("pageSize", 50)),
                )
                return result(
                    request_id,
                    {
                        "tasks": [
                            public_task(task_item)
                            for task_item in page["tasks"]
                        ],
                        "nextCursor": page["nextCursor"],
                        "totalSize": page["totalSize"],
                    },
                )
            if method == "tasks/result":
                return self.task_result(
                    request_id,
                    str(params.get("taskId", "")),
                )
            if method == "tasks/cancel":
                return result(
                    request_id,
                    public_task(
                        self.tasks.cancel(str(params.get("taskId", "")))
                    ),
                )
            return None if is_notification else error(
                request_id,
                -32601,
                f"Method not found: {method}",
            )
        except GgenCreateError as exc:
            if is_notification:
                return None
            code = {
                "TASK_NOT_FOUND_REFUSED": -32001,
                "TASK_NOT_CANCELABLE_REFUSED": -32002,
                "TASK_EXPIRED_REFUSED": -32003,
                "MCP_LIFECYCLE_REFUSED": -32004,
                "MCP_TASKS_NOT_NEGOTIATED_REFUSED": -32005,
                "MCP_TASK_UNSUPPORTED_REFUSED": -32006,
            }.get(exc.code, -32602)
            return error(
                request_id,
                code,
                exc.code,
                {"detail": exc.detail},
            )
        except Exception as exc:
            if is_notification:
                return None
            return error(
                request_id,
                -32603,
                "Internal error",
                {"type": type(exc).__name__, "detail": str(exc)},
            )

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in TOOL_BY_NAME:
            return tool_result(
                {"code": "UNKNOWN_TOOL_REFUSED", "detail": str(name)},
                is_error=True,
            )
        if not isinstance(arguments, dict):
            return tool_result(
                {
                    "code": "TOOL_ARGUMENTS_REFUSED",
                    "detail": "arguments must be an object",
                },
                is_error=True,
            )
        try:
            validate_schema(arguments, TOOL_BY_NAME[name]["inputSchema"])
        except GgenCreateError as exc:
            return tool_result(
                {"code": exc.code, "detail": exc.detail},
                is_error=True,
            )

        task_request = params.get("task")
        if task_request is None:
            return self.execute(name, arguments)
        self.require_tasks()
        if TOOL_BY_NAME[name]["execution"]["taskSupport"] == "forbidden":
            raise GgenCreateError("MCP_TASK_UNSUPPORTED_REFUSED", name)
        if not isinstance(task_request, dict):
            raise GgenCreateError(
                "MCP_TASK_REQUEST_REFUSED",
                "task must be an object",
            )
        ttl_value = task_request.get("ttl", 300_000)
        task_item = self.tasks.create(
            kind="tools/call",
            request={"name": name, "arguments": arguments},
            ttl=None if ttl_value is None else int(ttl_value),
            poll_interval=int(task_request.get("pollInterval", 250)),
        )
        worker = threading.Thread(
            target=self.run_task,
            args=(task_item["taskId"], name, arguments),
            name=f"ggen-create-mcp-{task_item['taskId']}",
            daemon=True,
        )
        worker.start()
        return {"task": public_task(task_item)}

    def run_task(
        self,
        task_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        try:
            current = self.tasks.get(task_id)
            if current["status"] != "working":
                return
            value = self.execute(name, arguments)
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
            if exc.code in {
                "TASK_TRANSITION_REFUSED",
                "TASK_NOT_FOUND_REFUSED",
                "TASK_EXPIRED_REFUSED",
            }:
                return
            self.fail_task(
                task_id,
                {
                    "rpcCode": -32603,
                    "message": exc.code,
                    "data": {"detail": exc.detail},
                },
            )
        except Exception as exc:
            self.fail_task(
                task_id,
                {
                    "rpcCode": -32603,
                    "message": "Internal error",
                    "data": {
                        "type": type(exc).__name__,
                        "detail": str(exc),
                    },
                },
            )

    def fail_task(self, task_id: str, failure: dict[str, Any]) -> None:
        try:
            current = self.tasks.get(task_id)
            if current["status"] == "working":
                self.tasks.fail(task_id, failure)
        except GgenCreateError:
            return

    def task_result(
        self,
        request_id: Any,
        task_id: str,
    ) -> dict[str, Any]:
        task_item = self.tasks.get(task_id)
        metadata = related_task(task_id)
        if task_item["status"] == "completed":
            value = task_item["result"]
            if isinstance(value, dict):
                value = dict(value)
                value["_meta"] = metadata
            else:
                value = {"value": value, "_meta": metadata}
            return result(request_id, value)
        if task_item["status"] in self.tasks.INTERRUPTED:
            return result(
                request_id,
                {"request": task_item["result"], "_meta": metadata},
            )
        if task_item["status"] in {"failed", "rejected"}:
            failure = task_item.get("error") or {}
            return error(
                request_id,
                int(failure.get("rpcCode", -32603)),
                str(failure.get("message", "Task failed")),
                {**(failure.get("data") or {}), "_meta": metadata},
            )
        if task_item["status"] == "cancelled":
            return error(
                request_id,
                -32002,
                "Task cancelled",
                {"_meta": metadata},
            )
        return error(
            request_id,
            -32000,
            "Task not ready",
            {
                "status": task_item["status"],
                "pollInterval": task_item.get("pollInterval"),
                "_meta": metadata,
            },
        )

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            session_path = self.session(arguments)
            broker = Broker(self.root)
            confirm = bool(arguments.get("confirm", False))
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
                            "output_root": arguments.get("output_root", "_ggen"),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get("variation_value"),
                        },
                    ),
                    session_path=session_path,
                )
            elif name == "ggen_create_package_verify":
                value = broker.execute(
                    self.registry.plan(
                        "package.verify",
                        {
                            "output_root": arguments.get("output_root", "_ggen"),
                            "package": arguments.get("package"),
                        },
                    ),
                    session_path=session_path,
                )
            elif name == "ggen_create_apply":
                value = broker.execute(
                    self.registry.plan(
                        "automatic.create",
                        {
                            "output_root": arguments.get("output_root", "_ggen"),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get("variation_value"),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                            "force": bool(arguments.get("force", False)),
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
                            "output_root": arguments.get("output_root", "_ggen"),
                            "cycles": int(arguments.get("cycles", 2)),
                            "interval_seconds": float(
                                arguments.get("interval_seconds", 0)
                            ),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get("variation_value"),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                            "force": bool(arguments.get("force", False)),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name in {
                "ggen_create_autonomic_cycle",
                "ggen_create_autonomic_run",
            }:
                skill_name = (
                    "autonomic.cycle"
                    if name.endswith("cycle")
                    else "autonomic.run"
                )
                value = broker.execute(
                    self.registry.plan(
                        skill_name,
                        {
                            "output_root": arguments.get("output_root", "_ggen"),
                            "max_cycles": int(arguments.get("max_cycles", 4)),
                            "stable_cycles": int(arguments.get("stable_cycles", 2)),
                            "interval_seconds": float(
                                arguments.get("interval_seconds", 0)
                            ),
                            "apply": bool(arguments.get("apply", True)),
                            "verify": bool(arguments.get("verify", False)),
                            "variation_value": arguments.get("variation_value"),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                        },
                    ),
                    session_path=session_path,
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
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_selfplay":
                value = broker.execute(
                    self.registry.plan(
                        "selfplay.run",
                        {
                            "output_root": arguments.get(
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
                            "output_root": arguments.get(
                                "output_root",
                                ".ggen-create/parity",
                            ),
                            "variation_value": arguments.get("variation_value"),
                            "ggen_bin": arguments.get("ggen_bin", "ggen"),
                            "sync_args": arguments.get("sync_args"),
                            "reference_dir": arguments.get("reference_dir"),
                            "reference_id": arguments.get("reference_id"),
                            "force": bool(arguments.get("force", True)),
                        },
                    ),
                    session_path=session_path,
                    confirm=confirm,
                )
            elif name == "ggen_create_receipt_verify":
                value = broker.execute(
                    self.registry.plan(
                        "receipt.verify",
                        {"path": arguments.get("path")},
                    ),
                    session_path=session_path,
                )
            elif name == "ggen_create_receipt_chain_verify":
                value = broker.execute(
                    self.registry.plan("receipt.chain.verify", {}),
                    session_path=session_path,
                )
            elif name == "ggen_create_doctor":
                from .doctor import doctor_report

                value = doctor_report(
                    self.root,
                    project=str(arguments.get("project", SESSION_FILE)),
                )
            else:
                raise GgenCreateError("UNKNOWN_TOOL_REFUSED", name)
            return tool_result(value)
        except GgenCreateError as exc:
            return tool_result(
                {"code": exc.code, "detail": exc.detail},
                is_error=True,
            )
        except Exception as exc:
            return tool_result(
                {
                    "code": "TOOL_INTERNAL_ERROR",
                    "type": type(exc).__name__,
                    "detail": str(exc),
                },
                is_error=True,
            )

    @staticmethod
    def resources() -> list[dict[str, Any]]:
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
                "title": "Canonical create-time skills",
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
                "title": "Latest native receipt",
                "mimeType": "application/json",
            },
            {
                "uri": "ggen-create://receipts/chain",
                "name": "receipt-chain",
                "title": "Native receipt ledger verification",
                "mimeType": "application/json",
            },
            {
                "uri": "ggen-create://doctor",
                "name": "doctor",
                "title": "Evidence-backed runtime standing",
                "mimeType": "application/json",
            },
        ]

    def read_resource(self, uri: str) -> dict[str, Any]:
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
    def prompts() -> list[dict[str, Any]]:
        return [
            {
                "name": "create-factory",
                "title": "Create an admitted factory",
                "description": "Inspect, plan, apply, verify, and receipt.",
                "arguments": [{"name": "goal", "required": True}],
            },
            {
                "name": "repair-factory",
                "title": "Repair a drifting factory",
                "description": "Use bounded integrity-aware autonomic convergence.",
                "arguments": [{"name": "symptom", "required": True}],
            },
            {
                "name": "certify-factory",
                "title": "Calculate standing",
                "description": "Verify package, receipts, tasks, and authority.",
                "arguments": [],
            },
        ]

    @staticmethod
    def prompt(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
                f"Goal: {goal}. Inspect and plan first. Request explicit "
                "confirmation before any native actuation."
            )
        elif name == "repair-factory":
            symptom = arguments.get("symptom")
            if not isinstance(symptom, str) or not symptom.strip():
                raise GgenCreateError(
                    "PROMPT_ARGUMENTS_REFUSED",
                    "symptom is required",
                )
            text = (
                f"Symptom: {symptom}. Diagnose package integrity and exemplar "
                "drift, then run a bounded confirmed autonomic loop."
            )
        elif name == "certify-factory":
            text = (
                "Run doctor, package integrity, and receipt-chain verification. "
                "State the narrowest defensible standing; UNKNOWN is not ALIVE."
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
            response = error(None, -32700, "Parse error", str(exc))
        else:
            if not isinstance(request, dict):
                response = error(None, -32600, "JSON-RPC object required")
            else:
                response = server.handle(request)
        if response is not None:
            sys.stdout.write(
                json.dumps(
                    response,
                    separators=(",", ":"),
                    default=str,
                )
                + "\n"
            )
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-mcp")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    raise SystemExit(stdio_main(Path(args.root)))
