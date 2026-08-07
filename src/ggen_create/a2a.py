"""Stable public import surface for the complete A2A runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .a2a_runtime import (
    A2A_PROTOCOL_VERSION,
    MAX_REQUEST_BYTES,
    SERVER_VERSION,
    A2AHttpServer,
    A2AService as _A2AService,
    handler,
    message_data,
    message_text,
)
from .model import GgenCreateError


class A2AService(_A2AService):
    """Public A2A service with explicit session-independent skill handling."""

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
            if operation == "doctor.inspect":
                arguments = data.get("arguments") or {}
                if not isinstance(arguments, dict):
                    raise GgenCreateError(
                        "A2A_ARGUMENTS_REFUSED",
                        "arguments must be an object",
                    )
                return operation, dict(arguments), False
        text = message_text(message)
        if default_operation is None and any(
            word in text.lower()
            for word in ("doctor", "standing", "health", "readiness")
        ):
            return "doctor.inspect", {"goal": text}, False
        return super().operation(
            message,
            default_operation=default_operation,
        )

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
                agent_name = (
                    "certifier"
                    if operation == "doctor.inspect"
                    else self._agent_for(operation)
                )
                session_path = (
                    self.session(arguments) if skill.requires_session else None
                )
                execution = self.agents.dispatch(
                    agent_name,
                    operation,
                    arguments,
                    session_path=session_path,
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

    @staticmethod
    def _agent_for(operation: str) -> str:
        from .a2a_runtime import SKILL_AGENT

        try:
            return SKILL_AGENT[operation]
        except KeyError as exc:
            raise GgenCreateError("A2A_OPERATION_REFUSED", operation) from exc


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
    advertised = args.base_url or f"http://{args.host}:{args.port}"
    if args.card:
        print(
            json.dumps(
                A2AService(
                    Path(args.root),
                    base_url=advertised,
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


__all__ = [
    "A2A_PROTOCOL_VERSION",
    "MAX_REQUEST_BYTES",
    "SERVER_VERSION",
    "A2AService",
    "main",
    "serve",
]


if __name__ == "__main__":
    main()
