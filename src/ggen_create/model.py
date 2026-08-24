from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

# This is the hygen-create-format compatibility marker (the session/capture schema
# version, written into every ggen-create.json and checked against
# SUPPORTED_SESSION_VERSIONS below), not the package release version in
# pyproject.toml. The two are intentionally decoupled: bumping this would change
# what session-format version this build claims to speak - including, downstream,
# the producer.version field ggen-legacy's receiving-contract authority pins
# (authority/ggen-create-receiving-contract.json in that repo) - which is a
# session-compatibility decision, not something that should track every package
# release automatically.
APP_VERSION = "0.4.0"
# Phase 2 (multiple seeds, product/PRD.md "Infer -- Phase 2: multiple seeds"): a session is
# migrated in place from APP_VERSION to MULTI_SEED_VERSION only when a second seed is added
# (session.py::add_seed) -- a plain `start`/`usename` session stays at APP_VERSION, byte-
# identical to before this phase, per this phase's own back-compat requirement.
MULTI_SEED_VERSION = "0.5.0"
SUPPORTED_SESSION_VERSIONS = (
    "0.2.0",
    "0.2.1",
    "0.3.0",
    APP_VERSION,
    MULTI_SEED_VERSION,
)
SESSION_FILE = "ggen-create.json"
ABOUT = (
    "This is a hygen-create definitions file. The hygen-create utility creates "
    "generators that can be executed using hygen."
)

_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9 _.-]{0,126}[A-Za-z0-9])?\Z"
)
_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class GgenCreateError(RuntimeError):
    """Typed refusal raised by every unlawful create-time transition."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.detail = message
        super().__init__(f"{code}: {message}")


def validate_identifier(
    value: Any,
    *,
    code: str = "IDENTIFIER_REFUSED",
    label: str = "identifier",
) -> str:
    """Admit a bounded cross-platform logical name before path actuation."""

    if not isinstance(value, str) or not value:
        raise GgenCreateError(code, f"{label} must be a non-empty string")
    if value != value.strip():
        raise GgenCreateError(code, f"{label} must not have edge whitespace")
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise GgenCreateError(
            code,
            f"{label} may contain ASCII letters, digits, internal spaces, "
            "underscore, hyphen, and dot only; length must be at most 128",
        )
    stem = value.split(".", 1)[0].upper()
    if stem in _WINDOWS_DEVICE_NAMES:
        raise GgenCreateError(
            code,
            f"{label} is a reserved cross-platform device name: {value!r}",
        )
    return value


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
