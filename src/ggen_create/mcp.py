"""Stable public import surface for the complete MCP runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .mcp_runtime import (
    MCP_PROTOCOL_VERSION,
    RELATED_TASK_KEY,
    SERVER_NAME,
    SERVER_VERSION,
    TOOLS,
    McpServer as _McpServer,
    error,
    tool_result,
)
from .skills import Broker, SkillRegistry


_GLOBAL_TO_SKILL = {
    "ggen_create_agent_route": "agents.route",
    "ggen_create_receipt_verify": "receipt.verify",
    "ggen_create_receipt_chain_verify": "receipt.chain.verify",
    "ggen_create_doctor": "doctor.inspect",
}


class McpServer(_McpServer):
    """Public server with compatibility normalization at the protocol edge."""

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(arguments)
        if name == "ggen_create_package_verify" and normalized.get("package") is None:
            normalized.pop("package", None)

        skill_name = _GLOBAL_TO_SKILL.get(name)
        if skill_name is not None:
            try:
                registry = SkillRegistry()
                value = Broker(self.root).execute(
                    registry.plan(skill_name, normalized),
                    session_path=None,
                )
                return tool_result(value)
            except Exception as exc:
                from .model import GgenCreateError

                if isinstance(exc, GgenCreateError):
                    return tool_result(
                        {"code": exc.code, "detail": exc.detail},
                        is_error=True,
                    )
                return tool_result(
                    {
                        "code": "TOOL_INTERNAL_ERROR",
                        "type": type(exc).__name__,
                        "detail": str(exc),
                    },
                    is_error=True,
                )
        return super().execute(name, normalized)


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


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "RELATED_TASK_KEY",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOLS",
    "McpServer",
    "main",
    "stdio_main",
]


if __name__ == "__main__":
    main()
