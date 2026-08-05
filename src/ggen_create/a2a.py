from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .agents import AGENTS, AgentRuntime
from .model import GgenCreateError, SESSION_FILE
from .runtime import TaskStore
from .session import find_session

A2A_PROTOCOL_VERSION = "1.0"

_SKILL_AGENT = {
    "capture.inspect": "receiver",
    "automatic.plan": "manufacturing-architect",
    "package.build": "manufacturing-architect",
    "automatic.create": "manufacturing-architect",
    "autonomic.run": "manufacturing-architect",
    "parity.verify": "verification-architect",
    "selfplay.run": "adversarial-verifier",
    "receipt.verify": "certifier",
    "skills.list": "skill-architect",
    "agents.list": "topology-architect",
    "agents.route": "topology-architect",
}
_TEXT_ROUTES = (
    (("selfplay", "adversarial", "red team"), "selfplay.run"),
    (("parity", "verify", "test"), "parity.verify"),
    (("autonomic", "repair", "heal", "converge"), "autonomic.run"),
    (("manufacture", "build", "automatic", "package"), "automatic.plan"),
    (("receipt", "certify"), "receipt.verify"),
    (("skill",), "skills.list"),
    (("agent", "route", "topology"), "agents.route"),
    (("inspect", "capture"), "capture.inspect"),
)


def _result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    value: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        value["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": value}


def _state(status: str) -> str:
    return {
        "working": "TASK_STATE_WORKING",
        "input_required": "TASK_STATE_INPUT_REQUIRED",
        "completed": "TASK_STATE_COMPLETED",
        "failed": "TASK_STATE_FAILED",
        "cancelled": "TASK_STATE_CANCELED",
    }.get(status, "TASK_STATE_UNSPECIFIED")


def _task(task: dict[str, Any]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if task.get("result") is not None:
        artifacts.append({
            "artifactId": f"artifact-{task['taskId']}",
            "name": "ggen-create-result",
            "description": "Receipt-backed create-time result.",
            "parts": [
                {"data": task["result"], "mediaType": "application/json"},
                {"text": json.dumps(task["result"], indent=2, sort_keys=True, default=str)},
            ],
        })
    value = {
        "id": task["taskId"],
        "contextId": task.get("contextId") or task["taskId"],
        "status": {
            "state": _state(task["status"]),
            "message": {
                "messageId": f"status-{task['taskId']}",
                "role": "ROLE_AGENT",
                "parts": [{"text": task.get("statusMessage", "")}],
            },
            "timestamp": task["lastUpdatedAt"],
        },
        "artifacts": artifacts,
        "metadata": {"kind": task.get("kind"), "ttl": task.get("ttl"), "pollInterval": task.get("pollInterval")},
    }
    if task.get("error") is not None:
        value["metadata"]["error"] = task["error"]
    return value


def _text(message: dict[str, Any]) -> str:
    return "\n".join(part["text"] for part in message.get("parts", []) if isinstance(part, dict) and isinstance(part.get("text"), str))


def _data(message: dict[str, Any]) -> dict[str, Any] | None:
    for part in message.get("parts", []):
        if isinstance(part, dict) and isinstance(part.get("data"), dict):
            return dict(part["data"])
    return None


def _route_text(text: str) -> str:
    normalized = text.lower()
    matches: list[tuple[int, str]] = []
    for keywords, skill in _TEXT_ROUTES:
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score:
            matches.append((score, skill))
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

    def agent_card(self) -> dict[str, Any]:
        return {
            "name": "ggen-create",
            "description": "Reverse-compile working exemplars into admitted ggen factories using bounded skills, agents, autonomic control, and receipts.",
            "version": "0.3.0",
            "supportedInterfaces": [{"url": f"{self.base_url}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": A2A_PROTOCOL_VERSION}],
            "capabilities": {"streaming": False, "pushNotifications": False, "extendedAgentCard": False},
            "defaultInputModes": ["text/plain", "application/json"],
            "defaultOutputModes": ["text/plain", "application/json"],
            "skills": [
                {
                    "id": agent.name,
                    "name": agent.name.replace("-", " ").title(),
                    "description": agent.role,
                    "tags": ["ggen-create", "factory", "gall", agent.name],
                    "examples": [f"Route work to {agent.name}", f"Produce {agent.produces}"],
                    "inputModes": ["text/plain", "application/json"],
                    "outputModes": ["text/plain", "application/json"],
                }
                for agent in AGENTS
            ],
        }

    def _session(self, arguments: dict[str, Any]) -> Path:
        project = str(arguments.pop("project", SESSION_FILE))
        if project in {"", ".", ".."} or "/" in project or "\\" in project:
            raise GgenCreateError("PROJECT_NAME_REFUSED", "project must be a capture filename")
        return find_session(self.root, project)

    def _operation(self, message: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
        data = _data(message)
        if data is not None:
            operation = str(data.get("operation", "")).strip()
            arguments = data.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise GgenCreateError("A2A_ARGUMENTS_REFUSED", "arguments must be an object")
            if operation not in _SKILL_AGENT:
                raise GgenCreateError("A2A_OPERATION_REFUSED", operation)
            return operation, dict(arguments), bool(data.get("confirm", False))
        text = _text(message)
        return _route_text(text), {"goal": text}, False

    def send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("parts"), list) or not message["parts"]:
            raise GgenCreateError("A2A_MESSAGE_REFUSED", "message with non-empty parts required")
        operation, arguments, confirm = self._operation(message)
        session = self._session(arguments)
        context_id = str(message.get("contextId") or params.get("contextId") or uuid4())
        task = self.tasks.create(kind=operation, request={"message": message, "arguments": arguments}, context_id=context_id)
        try:
            if operation == "agents.route":
                result = self.agents.route(str(arguments.get("goal", _text(message))), arguments.get("context", {}))
            else:
                result = self.agents.dispatch(_SKILL_AGENT[operation], operation, arguments, session_path=session, confirm=confirm)
            task = self.tasks.complete(task["taskId"], result)
        except GgenCreateError as exc:
            task = self.tasks.fail(task["taskId"], {"code": exc.code, "detail": exc.detail})
        return {"task": _task(task)}

    def handle_rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                return _error(request_id, -32600, "Invalid Request")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                return _error(request_id, -32602, "Invalid parameters")
            method = request["method"]
            if method == "SendMessage":
                return _result(request_id, self.send_message(params))
            if method == "GetTask":
                return _result(request_id, {"task": _task(self.tasks.get(str(params.get("id", ""))))})
            if method == "ListTasks":
                return _result(request_id, {"tasks": [_task(task) for task in self.tasks.list()], "nextPageToken": ""})
            if method == "CancelTask":
                return _result(request_id, {"task": _task(self.tasks.cancel(str(params.get("id", ""))))})
            if method == "GetExtendedAgentCard":
                return _error(request_id, -32004, "Unsupported operation", {"reason": "EXTENDED_AGENT_CARD_UNSUPPORTED"})
            return _error(request_id, -32601, f"Method not found: {method}")
        except GgenCreateError as exc:
            code = {"TASK_NOT_FOUND_REFUSED": -32001, "TASK_NOT_CANCELABLE_REFUSED": -32002}.get(exc.code, -32602)
            return _error(request_id, code, exc.code, {"detail": exc.detail})
        except Exception as exc:
            return _error(request_id, -32603, "Internal error", {"type": type(exc).__name__, "detail": str(exc)})


def _handler(service: A2AService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: Any, content_type: str = "application/json") -> None:
            body = json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/.well-known/agent-card.json":
                self._json(200, service.agent_card(), "application/json")
            elif parsed.path == "/healthz":
                self._json(200, {"state": "ALIVE", "protocolVersion": A2A_PROTOCOL_VERSION})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/a2a":
                self._json(404, {"error": "not found"})
                return
            requested = self.headers.get("A2A-Version")
            if requested and requested != A2A_PROTOCOL_VERSION:
                self._json(400, _error(None, -32009, "Version not supported", {"requested": requested, "supported": A2A_PROTOCOL_VERSION}))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, _error(None, -32700, "Invalid JSON payload", str(exc)))
                return
            self._json(200, service.handle_rpc(payload))

        def log_message(self, format: str, *args: Any) -> None:
            super().log_message(format, *args)

    return Handler


def serve(root: Path, *, host: str = "127.0.0.1", port: int = 8765, base_url: str | None = None) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise GgenCreateError("A2A_NON_LOOPBACK_REFUSED", "the built-in A2A transport is unauthenticated and may bind only to loopback")
    if not 0 <= port <= 65535:
        raise GgenCreateError("A2A_PORT_REFUSED", str(port))
    advertised = base_url or f"http://{host}:{port}"
    ThreadingHTTPServer((host, port), _handler(A2AService(root, base_url=advertised))).serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-a2a")
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--base-url")
    parser.add_argument("--card", action="store_true")
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(A2AService(Path(args.root), base_url=args.base_url or f"http://{args.host}:{args.port}").agent_card(), indent=2, sort_keys=True))
        return
    serve(Path(args.root), host=args.host, port=args.port, base_url=args.base_url)


if __name__ == "__main__":
    main()
