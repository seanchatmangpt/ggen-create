"""Compatibility import surface for the complete MCP runtime."""

from .mcp_runtime import (
    MCP_PROTOCOL_VERSION,
    RELATED_TASK_KEY,
    SERVER_NAME,
    SERVER_VERSION,
    TOOLS,
    McpServer,
    main,
    stdio_main,
)

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
