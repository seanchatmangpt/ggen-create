from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_VERSION = "0.4.0"
SUPPORTED_SESSION_VERSIONS = (
    "0.2.0",
    "0.2.1",
    "0.3.0",
    APP_VERSION,
)
SESSION_FILE = "ggen-create.json"
ABOUT = (
    "This is a hygen-create definitions file. The hygen-create utility creates "
    "generators that can be executed using hygen."
)


class GgenCreateError(RuntimeError):
    """Typed refusal raised by every unlawful create-time transition."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.detail = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class Replacement:
    start: int
    end: int
    old_text: str
    transform: str
    variable: str

    def to_json(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "old_text": self.old_text,
            "transform": self.transform,
            "variable": self.variable,
        }


@dataclass(frozen=True)
class BuildResult:
    package_dir: Path
    changed: bool
    archived_previous: Path | None
    receipt_path: Path
