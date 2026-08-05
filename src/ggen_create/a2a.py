"""Compatibility import surface for the complete A2A runtime."""

from .a2a_runtime import (
    A2A_PROTOCOL_VERSION,
    MAX_REQUEST_BYTES,
    SERVER_VERSION,
    A2AService,
    main,
    serve,
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
