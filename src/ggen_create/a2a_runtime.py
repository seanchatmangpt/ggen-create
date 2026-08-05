from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .agents import AGENTS, AgentRuntime
from .model import APP_VERSION, GgenCreateError, SESSION_FILE
from .runtime import TaskStore, digest_json
from .session import find_session
from .skills import SkillRegistry

A2A_PROTOCOL_VERSION = "1.0"
SERVER_VERSION = APP_VERSION
MAX_REQUEST_BYTES = 1024 * 1024

SKILL_AGENT = {
    "capture.inspect": "receiver",
    "automatic.plan": "manufacturing-architect",
    "package.build": "manufacturing-architect",
    "package.verify": "certifier",
    "automatic.create": "manufacturing-architect",
    "automatic.watch": "manufacturing-architect",
    "autonomic.cycle": "manufacturing-architect",
    "autonomic.run": "manufacturing-architect",
    "parity.verify": "verification-architect",
    "selfplay.run": "adversarial-verifier",
    "receipt.verify": "certifier",
    "receipt.chain.verify": "certifier",
    "skills.list": "skill-architect",
    "agents.list": "topology-architect",
    "agents.route": "topology-architect",
}
TEXT_ROUTES = (
    (("selfplay", "adversarial", "red team"), "selfplay.run"),
    (("parity", "verify", "test"), "parity.verify"),
    (("watch", "observe changes"), "automatic.watch"),
    (("autonomic", "repair", "heal", "converge"), "autonomic.run"),
    (("integrity", "corrupt"), "package.verify"),
    (("manufacture", "build", "automatic", "package"), "automatic.plan"),
    (("receipt chain", "ledger"), "receipt.chain.verify"),
    (("receipt", "certify"), "receipt.verify"),
    (("skill",), "skills.list"),
    (("agent", "route", "topology"), "agents.route"),
    (("inspect", "capture"), "capture.inspect"),
)
EXTERNAL_TO_INTERNAL_STATE = {
    "TASK_STATE_WORKING": "working",
    "TASK_STATE_INPUT_REQUIRED": "input_required",
    "TASK_STATE_AUTH_REQUIRED": "auth_required",
    "TASK_STATE_COMPLETED": "completed",
    "TASK_STATE_FAILED": "failed",
    "TASK_STATE_CANCELED": "cancelled",
    "TASK_STATE_CANCELLED": "cancelled",
    "TASK_STATE_REJECTED": "rejected",
}


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


def external_state(status: str) -> str:
    return {
        "working": "TASK_STATE_WORKING",
        "input_required": "TASK_STATE_INPUT_REQUIRED",
        "auth_required": "TASK_STATE_AUTH_REQUIRED",
        "completed": "TASK_STATE_COMPLETED",
        "failed": "TASK_STATE_FAILED",
        "cancelled": "TASK_STATE_CANCELED",
        "rejected": "TASK_STATE_REJECTED",
    }.get(status, "TASK_STATE_UNSPECIFIED")


def history(
    task: dict[str, Any],
    history_length: int | None,
) -> list[dict[str, Any]]:
    if history_length is None:
        return []
    length = max(0, min(int(history_length), 100))
    if length == 0:
        return []
    values: list[dict[str, Any]] = []
    for entry in task.get("history", [])[-length:]:
        message = entry.get("message") if isinstance(entry, dict) else None
        if isinstance(message, dict):
            values.append(message)
    return values


def public_task(
    task: dict[str, Any],
    *,
    history_length: int | None = None,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if task.get("result") is not None and task.get("status") == "completed":
        artifacts.append(
            {
                "artifactId": f"artifact-{task['taskId']}",
                "name": "ggen-create-result",
                "description": "Receipt-backed create-time result.",
                "parts": [
                    {
                        "data": task["result"],
                        "mediaType": "application/json",
                    },
                    {
                        "text": json.dumps(
                            task["result"],
                            indent=2,
                            sort_keys=True,
                            default=str,
                        )
                    },
                ],
            }
        )
    value: dict[str, Any] = {
        "id": task["taskId"],
        "contextId": task.get("contextId") or task["taskId"],
        "status": {
            "state": external_state(task["status"]),
            "message": {
                "messageId": f"status-{task['taskId']}",
                "role": "ROLE_AGENT",
                "parts": [{"text": task.get("statusMessage", "")}],
            },
            "timestamp": task["lastUpdatedAt"],
        },
        "artifacts": artifacts,
        "metadata": {
            "kind": task.get("kind"),
            "ttl": task.get("ttl"),
            "pollInterval": task.get("pollInterval"),
        },
    }
    task_history = history(task, history_length)
    if task_history:
        value["history"] = task_history
    if task.get("error") is not None:
        value["metadata"]["error"] = task["error"]
    if task.get("status") in TaskStore.INTERRUPTED:
        value["metadata"]["request"] = task.get("result")
    return value


def validate_message(message: dict[str, Any]) -> None:
    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise GgenCreateError("A2A_MESSAGE_REFUSED", "messageId is required")
    if message.get("role") not in {"ROLE_USER", "user"}:
        raise GgenCreateError(
            "A2A_MESSAGE_REFUSED",
            "only user messages are accepted",
        )
    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        raise GgenCreateError(
            "A2A_MESSAGE_REFUSED",
            "message with non-empty parts required",
        )
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise GgenCreateError(
                "A2A_MESSAGE_REFUSED",
                f"part {index} must be an object",
            )
        content_keys = [
            key for key in ("text", "data", "raw", "url") if key in part
        ]
        if len(content_keys) != 1:
            raise GgenCreateError(
                "A2A_MESSAGE_REFUSED",
                f"part {index} must contain exactly one content field",
            )
        key = content_keys[0]
        if key == "text" and not isinstance(part[key], str):
            raise GgenCreateError(
                "A2A_MESSAGE_REFUSED",
                f"part {index}.text must be a string",
            )
        if key == "data" and not isinstance(part[key], dict):
            raise GgenCreateError(
                "A2A_MESSAGE_REFUSED",
                f"part {index}.data must be an object",
            )


def message_text(message: dict[str, Any]) -> str:
    return "\n".join(
        part["text"]
        for part in message.get("parts", [])
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def message_data(message: dict[str, Any]) -> dict[str, Any] | None:
    for part in message.get("parts", []):
        if isinstance(part, dict) and isinstance(part.get("data"), dict):
            return dict(part["data"])
    return None


def route_text(text: str) -> str:
    normalized = text.lower()
    matches: list[tuple[int, str]] = []
    for keywords, skill_name in TEXT_ROUTES:
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score:
            matches.append((score, skill_name))
    if not matches:
        return "capture.inspect"
    matches.sort(key=lambda item: (-item[0], item[1]))
    return matches[0][1]


class A2AService:
    def __init__(self, root: Path, *, base_url: str):
        self.root = root.resolve()
        self.base_url = base_url.rstrip("/")
        self.tasks = TaskStore(self.root, "a2a")
        self.agents = AgentRuntime(self.root)
        self.skills = SkillRegistry()

    def agent_card(self) -> dict[str, Any]:
        return {
            "name": "ggen-create",
            "description": (
                "Reverse-compile working exemplars into admitted ggen factories "
                "using bounded skills, agents, autonomic control, and receipts."
            ),
            "version": SERVER_VERSION,
            "supportedInterfaces": [
                {
                    "url": f"{self.base_url}/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": A2A_PROTOCOL_VERSION,
                }
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": ["text/plain", "application/json"],
            "defaultOutputModes": ["text/plain", "application/json"],
            "skills": [
                {
                    "id": agent.name,
                    "name": agent.name.replace("-", " ").title(),
                    "description": agent.role,
                    "tags": ["ggen-create", "factory", "gall", agent.name],
                    "examples": [
                        f"Route work to {agent.name}",
                        f"Produce {agent.produces}",
                    ],
                    "inputModes": ["text/plain", "application/json"],
                    "outputModes": ["text/plain", "application/json"],
                }
                for agent in AGENTS
            ],
        }

    def card_etag(self) -> str:
        return '"' + digest_json(self.agent_card()) + '"'

    def session(self, arguments: dict[str, Any]) -> Path:
        project = str(arguments.get("project", SESSION_FILE))
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError(
                "PROJECT_NAME_REFUSED",
                "project must be a capture filename",
            )
        return find_session(self.root, project)

    def operation(
        self,
        message: dict[str, Any],
        *,
        default_operation: str | None = None,
    ) -> tuple[str, dict[str, Any], bool]:
        data = message_data(message)
        if data is not None:
            operation = str(
                data.get("operation", default_operation or "")
            ).strip()
            arguments = data.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise GgenCreateError(
                    "A2A_ARGUMENTS_REFUSED",
                    "arguments must be an object",
                )
            if operation not in SKILL_AGENT:
                raise GgenCreateError("A2A_OPERATION_REFUSED", operation)
            confirm = bool(
                data.get("confirm", arguments.get("confirm", False))
            )
            return operation, dict(arguments), confirm
        text = message_text(message)
        return default_operation or route_text(text), {"goal": text}, False

    def execute_task(
        self,
        task: dict[str, Any],
        *,
        operation: str,
        arguments: dict[str, Any],
        confirm: bool,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            skill = self.skills.get(operation)
            if skill.requires_confirmation and not confirm:
                return self.tasks.require_input(
                    task["taskId"],
                    {
                        "operation": operation,
                        "required": {"confirm": True},
                        "message": (
                            "Repeat SendMessage with this taskId and confirm:true."
                        ),
                    },
                )
            if operation == "agents.route":
                execution = self.agents.route(
                    str(arguments.get("goal", message_text(message))),
                    arguments.get("context", {}),
                )
            else:
                execution = self.agents.dispatch(
                    SKILL_AGENT[operation],
                    operation,
                    arguments,
                    session_path=self.session(arguments),
                    confirm=confirm,
                )
            return self.tasks.complete(task["taskId"], execution)
        except GgenCreateError as exc:
            if exc.code in {
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
                "VARIATION_REQUIRED_REFUSED",
            }:
                return self.tasks.require_input(
                    task["taskId"],
                    {
                        "operation": operation,
                        "code": exc.code,
                        "detail": exc.detail,
                    },
                )
            return self.tasks.fail(
                task["taskId"],
                {"code": exc.code, "detail": exc.detail},
            )
        except Exception as exc:
            return self.tasks.fail(
                task["taskId"],
                {
                    "code": "A2A_INTERNAL_ERROR",
                    "type": type(exc).__name__,
                    "detail": str(exc),
                },
            )

    def send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, dict):
            raise GgenCreateError(
                "A2A_MESSAGE_REFUSED",
                "message object required",
            )
        validate_message(message)
        task_id = message.get("taskId") or params.get("taskId")
        existing: dict[str, Any] | None = None
        if task_id is not None:
            existing = self.tasks.get(str(task_id))
            if existing["status"] not in self.tasks.INTERRUPTED:
                raise GgenCreateError(
                    "A2A_TASK_CONTINUATION_REFUSED",
                    f"task {task_id} is not awaiting input",
                )
        operation, arguments, confirm = self.operation(
            message,
            default_operation=(
                str(existing["kind"]) if existing is not None else None
            ),
        )
        context_id = str(
            message.get("contextId")
            or params.get("contextId")
            or (existing.get("contextId") if existing else None)
            or uuid4()
        )
        request = {
            "message": message,
            "arguments": arguments,
            "confirm": confirm,
        }
        if existing is None:
            task = self.tasks.create(
                kind=operation,
                request=request,
                context_id=context_id,
            )
        else:
            if existing.get("kind") != operation:
                raise GgenCreateError(
                    "A2A_OPERATION_DRIFT_REFUSED",
                    f"{existing.get('kind')} -> {operation}",
                )
            if existing.get("contextId") not in {None, context_id}:
                raise GgenCreateError(
                    "A2A_CONTEXT_DRIFT_REFUSED",
                    context_id,
                )
            previous = existing.get("request") or {}
            previous_arguments = previous.get("arguments") or {}
            merged = dict(previous_arguments)
            merged.update(arguments)
            arguments = merged
            request["arguments"] = arguments
            task = self.tasks.resume(existing["taskId"], request)
        task = self.execute_task(
            task,
            operation=operation,
            arguments=arguments,
            confirm=confirm,
            message=message,
        )
        return {"task": public_task(task)}

    def handle_rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            if request.get("jsonrpc") != "2.0" or not isinstance(
                request.get("method"), str
            ):
                return error(request_id, -32600, "Invalid Request")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                return error(request_id, -32602, "Invalid parameters")
            method = request["method"]
            if method == "SendMessage":
                return result(request_id, self.send_message(params))
            if method == "GetTask":
                task_id = str(params.get("id") or params.get("taskId") or "")
                raw_history_length = params.get("historyLength")
                return result(
                    request_id,
                    {
                        "task": public_task(
                            self.tasks.get(task_id),
                            history_length=(
                                int(raw_history_length)
                                if raw_history_length is not None
                                else None
                            ),
                        )
                    },
                )
            if method == "ListTasks":
                status = params.get("status")
                internal_status = (
                    EXTERNAL_TO_INTERNAL_STATE.get(str(status), str(status))
                    if status is not None
                    else None
                )
                page = self.tasks.query(
                    status=internal_status,
                    context_id=params.get("contextId"),
                    cursor=params.get("pageToken"),
                    page_size=int(params.get("pageSize", 50)),
                )
                return result(
                    request_id,
                    {
                        "tasks": [
                            public_task(task) for task in page["tasks"]
                        ],
                        "totalSize": page["totalSize"],
                        "pageSize": page["pageSize"],
                        "nextPageToken": page["nextCursor"] or "",
                    },
                )
            if method == "CancelTask":
                task_id = str(params.get("id") or params.get("taskId") or "")
                return result(
                    request_id,
                    {"task": public_task(self.tasks.cancel(task_id))},
                )
            if method == "GetExtendedAgentCard":
                return error(
                    request_id,
                    -32004,
                    "Unsupported operation",
                    {"reason": "EXTENDED_AGENT_CARD_UNSUPPORTED"},
                )
            return error(
                request_id,
                -32601,
                f"Method not found: {method}",
            )
        except GgenCreateError as exc:
            code = {
                "TASK_NOT_FOUND_REFUSED": -32001,
                "TASK_NOT_CANCELABLE_REFUSED": -32002,
                "TASK_EXPIRED_REFUSED": -32003,
                "A2A_TASK_CONTINUATION_REFUSED": -32004,
                "A2A_OPERATION_DRIFT_REFUSED": -32005,
                "A2A_CONTEXT_DRIFT_REFUSED": -32006,
            }.get(exc.code, -32602)
            return error(
                request_id,
                code,
                exc.code,
                {"detail": exc.detail},
            )
        except Exception as exc:
            return error(
                request_id,
                -32603,
                "Internal error",
                {"type": type(exc).__name__, "detail": str(exc)},
            )


def handler(service: A2AService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def send_json(
            self,
            status: int,
            value: Any = None,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = (
                b""
                if value is None
                else json.dumps(
                    value,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("A2A-Version", A2A_PROTOCOL_VERSION)
            for key, item in (headers or {}).items():
                self.send_header(key, item)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/.well-known/agent-card.json":
                etag = service.card_etag()
                cache_headers = {
                    "ETag": etag,
                    "Cache-Control": "public, max-age=300",
                }
                if self.headers.get("If-None-Match") == etag:
                    self.send_json(304, headers=cache_headers)
                    return
                self.send_json(
                    200,
                    service.agent_card(),
                    headers=cache_headers,
                )
            elif path == "/healthz":
                self.send_json(
                    200,
                    {
                        "state": "ALIVE",
                        "protocolVersion": A2A_PROTOCOL_VERSION,
                    },
                    headers={"Cache-Control": "no-store"},
                )
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/a2a":
                self.send_json(404, {"error": "not found"})
                return
            requested = self.headers.get("A2A-Version") or "0.3"
            if requested != A2A_PROTOCOL_VERSION:
                self.send_json(
                    400,
                    error(
                        None,
                        -32009,
                        "Version not supported",
                        {
                            "requested": requested,
                            "supported": A2A_PROTOCOL_VERSION,
                        },
                    ),
                )
                return
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("application/json"):
                self.send_json(
                    415,
                    error(None, -32600, "application/json required"),
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_json(
                    400,
                    error(None, -32600, "Invalid Content-Length"),
                )
                return
            if length < 0 or length > MAX_REQUEST_BYTES:
                self.send_json(
                    413,
                    error(
                        None,
                        -32600,
                        "Request body too large",
                        {"maximumBytes": MAX_REQUEST_BYTES},
                    ),
                )
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json(
                    400,
                    error(None, -32700, "Invalid JSON payload", str(exc)),
                )
                return
            if not isinstance(payload, dict):
                self.send_json(
                    400,
                    error(None, -32600, "JSON-RPC object required"),
                )
                return
            self.send_json(
                200,
                service.handle_rpc(payload),
                headers={"Cache-Control": "no-store"},
            )

        def log_message(self, format: str, *args: Any) -> None:
            super().log_message(format, *args)

    return Handler


class A2AHttpServer(ThreadingHTTPServer):
    daemon_threads = True


def serve(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    base_url: str | None = None,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise GgenCreateError(
            "A2A_NON_LOOPBACK_REFUSED",
            "the built-in A2A transport is unauthenticated and may bind only "
            "to loopback",
        )
    if not 0 <= port <= 65535:
        raise GgenCreateError("A2A_PORT_REFUSED", str(port))
    advertised = base_url or f"http://{host}:{port}"
    A2AHttpServer(
        (host, port),
        handler(A2AService(root, base_url=advertised)),
    ).serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-a2a")
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--base-url")
    parser.add_argument("--card", action="store_true")
    args = parser.parse_args(argv)
    if args.card:
        print(
            json.dumps(
                A2AService(
                    Path(args.root),
                    base_url=(
                        args.base_url
                        or f"http://{args.host}:{args.port}"
                    ),
                ).agent_card(),
                indent=2,
                sort_keys=True,
            )
        )
        return
    serve(
        Path(args.root),
        host=args.host,
        port=args.port,
        base_url=args.base_url,
    )
