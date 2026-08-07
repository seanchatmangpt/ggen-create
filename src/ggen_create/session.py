from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from .model import (
    ABOUT,
    APP_VERSION,
    GgenCreateError,
    SESSION_FILE,
    SUPPORTED_SESSION_VERSIONS,
    validate_identifier,
)

_SESSION_FIELDS = {
    "about",
    "hygen_create_version",
    "name",
    "files_and_dirs",
    "templatize_using_name",
    "gen_parent_dir",
}


def _session_template(name: str, filename: str) -> dict[str, Any]:
    return {
        "about": ABOUT,
        "hygen_create_version": APP_VERSION,
        "name": name,
        "files_and_dirs": {filename: True},
        "templatize_using_name": None,
        "gen_parent_dir": False,
    }


def save_session(path: Path, session: dict[str, Any]) -> None:
    ordered = dict(session)
    ordered["files_and_dirs"] = dict(
        sorted(session["files_and_dirs"].items(), key=lambda item: item[0])
    )
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def start_session(
    root: Path,
    name: str,
    filename: str = SESSION_FILE,
) -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise GgenCreateError(
            "CAPTURE_ROOT_MISSING_REFUSED",
            f"not a directory: {root}",
        )
    name = validate_identifier(
        name,
        code="GENERATOR_NAME_REFUSED",
        label="generator name",
    )
    filename = _validate_capture_path(filename)
    path = root / filename
    if path.exists():
        raise GgenCreateError(
            "SESSION_IN_PROGRESS_REFUSED",
            f"capture already exists: {path}",
        )
    save_session(path, _session_template(name, filename))
    return path


def find_session(start: Path, filename: str = SESSION_FILE) -> Path:
    filename = _validate_capture_path(filename)
    current = start.resolve()
    if current.is_file():
        current = current.parent
    while True:
        candidate = current / filename
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    raise GgenCreateError(
        "NO_SESSION_REFUSED",
        f"no {filename} found from {start}; run 'ggen-create start <name>'",
    )


def _validate_capture_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise GgenCreateError(
            "SESSION_PATH_REFUSED",
            "capture paths must be non-empty strings",
        )
    if "\x00" in value:
        raise GgenCreateError(
            "SESSION_PATH_REFUSED",
            f"capture path contains NUL: {value!r}",
        )
    normalized = value.replace("\\", "/")
    if normalized in {".", ".."}:
        raise GgenCreateError(
            "SESSION_PATH_REFUSED",
            f"capture path contains an unsafe segment: {value!r}",
        )
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise GgenCreateError(
            "SESSION_PATH_REFUSED",
            f"capture path must be relative: {value!r}",
        )
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise GgenCreateError(
            "SESSION_PATH_REFUSED",
            f"capture path contains an unsafe segment: {value!r}",
        )
    return posix.as_posix()


def _validate_session_document(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            f"capture must be an object: {path}",
        )
    fields = set(value)
    missing = sorted(_SESSION_FIELDS - fields)
    extras = sorted(fields - _SESSION_FIELDS)
    if missing or extras:
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            f"capture fields differ; missing={missing}, extras={extras}",
        )
    if value.get("about") != ABOUT:
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            "capture about field does not identify a hygen-create session",
        )
    version = value.get("hygen_create_version")
    if not isinstance(version, str):
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            "hygen_create_version must be a string",
        )
    if version not in SUPPORTED_SESSION_VERSIONS:
        raise GgenCreateError(
            "SESSION_VERSION_REFUSED",
            f"unsupported capture version {version!r}; supported: "
            + ", ".join(SUPPORTED_SESSION_VERSIONS),
        )
    value["name"] = validate_identifier(
        value.get("name"),
        code="GENERATOR_NAME_REFUSED",
        label="generator name",
    )
    files = value.get("files_and_dirs")
    if not isinstance(files, dict) or not files:
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            "files_and_dirs must be a non-empty object",
        )
    normalized_files: dict[str, bool] = {}
    for raw_path, included in files.items():
        rel = _validate_capture_path(raw_path)
        if rel in normalized_files:
            raise GgenCreateError(
                "SESSION_PATH_COLLISION_REFUSED",
                f"multiple capture paths normalize to {rel!r}",
            )
        if not isinstance(included, bool):
            raise GgenCreateError(
                "SESSION_SCHEMA_REFUSED",
                f"files_and_dirs[{raw_path!r}] must be boolean",
            )
        normalized_files[rel] = included
    value["files_and_dirs"] = normalized_files
    seed = value.get("templatize_using_name")
    if seed is not None:
        value["templatize_using_name"] = validate_identifier(
            seed,
            code="PARAMETER_SEED_REFUSED",
            label="parameter seed",
        )
    if not isinstance(value.get("gen_parent_dir"), bool):
        raise GgenCreateError(
            "SESSION_SCHEMA_REFUSED",
            "gen_parent_dir must be a boolean",
        )
    return value


def load_session(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError(
            "SESSION_PARSE_REFUSED",
            f"cannot parse {path}: {exc}",
        ) from exc
    return _validate_session_document(value, path)


def _is_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        chunk = handle.read(8192)
    return b"\0" in chunk


def _relative_under_root(root: Path, candidate: Path) -> str:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise GgenCreateError(
            "PATH_MISSING_REFUSED",
            f"cannot resolve {candidate}: {exc}",
        ) from exc
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise GgenCreateError(
            "PATH_OUTSIDE_CAPTURE_ROOT_REFUSED",
            f"{resolved} is outside capture root {root}",
        ) from exc


def _candidate_files(path: Path, recursive: bool) -> Iterable[Path]:
    if path.is_symlink():
        raise GgenCreateError(
            "SYMLINK_REFUSED",
            f"symlinks are not admitted: {path}",
        )
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        raise GgenCreateError(
            "PATH_MISSING_REFUSED",
            f"path not found: {path}",
        )
    for child in sorted(path.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            raise GgenCreateError(
                "SYMLINK_REFUSED",
                f"symlinks are not admitted: {child}",
            )
        if child.is_file():
            yield child
        elif child.is_dir() and recursive:
            yield from _candidate_files(child, recursive=True)


def add_paths(
    session_path: Path,
    raw_paths: list[str],
    *,
    recursive: bool = False,
    cwd: Path | None = None,
) -> list[str]:
    session = load_session(session_path)
    root = session_path.parent.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    added: list[str] = []
    for raw in raw_paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        for file_path in _candidate_files(candidate, recursive):
            rel = _relative_under_root(root, file_path)
            if _is_binary(file_path):
                raise GgenCreateError(
                    "BINARY_FILE_REFUSED",
                    f"binary file: {rel}",
                )
            try:
                file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise GgenCreateError(
                    "NON_UTF8_FILE_REFUSED",
                    f"file is not UTF-8 text: {rel}",
                ) from exc
            if session["files_and_dirs"].get(rel) is True:
                continue
            session["files_and_dirs"][rel] = True
            added.append(rel)
    save_session(session_path, session)
    return added


def remove_paths(
    session_path: Path,
    raw_paths: list[str],
    *,
    cwd: Path | None = None,
) -> list[str]:
    session = load_session(session_path)
    root = session_path.parent.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    removed: list[str] = []
    for raw in raw_paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        rel = _relative_under_root(root, candidate)
        if session["files_and_dirs"].pop(rel, None) is not None:
            removed.append(rel)
    save_session(session_path, session)
    return removed


def set_seed(session_path: Path, value: str) -> None:
    value = validate_identifier(
        value,
        code="PARAMETER_SEED_REFUSED",
        label="parameter seed",
    )
    session = load_session(session_path)
    session["templatize_using_name"] = value
    save_session(session_path, session)


def rename_session(session_path: Path, name: str) -> None:
    name = validate_identifier(
        name,
        code="GENERATOR_NAME_REFUSED",
        label="generator name",
    )
    session = load_session(session_path)
    session["name"] = name
    save_session(session_path, session)


def set_parent_dir(session_path: Path, enabled: bool) -> None:
    session = load_session(session_path)
    session["gen_parent_dir"] = enabled
    save_session(session_path, session)


def abort_session(session_path: Path) -> None:
    try:
        session_path.unlink()
    except OSError as exc:
        raise GgenCreateError(
            "SESSION_ABORT_REFUSED",
            str(exc),
        ) from exc


def admitted_files(session_path: Path) -> list[str]:
    session = load_session(session_path)
    root = session_path.parent.resolve()
    result: list[str] = []
    for rel, included in session["files_and_dirs"].items():
        if not included:
            continue
        path = root / rel
        if path.is_symlink():
            raise GgenCreateError(
                "SYMLINK_REFUSED",
                f"symlinks are not admitted: {rel}",
            )
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise GgenCreateError(
                "INCLUDED_PATH_MISSING_REFUSED",
                f"missing: {rel}: {exc}",
            ) from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise GgenCreateError(
                "PATH_OUTSIDE_CAPTURE_ROOT_REFUSED",
                f"{resolved} is outside capture root {root}",
            ) from exc
        if not resolved.is_file():
            raise GgenCreateError(
                "INCLUDED_PATH_MISSING_REFUSED",
                f"not a file: {rel}",
            )
        result.append(rel)
    if not result:
        raise GgenCreateError(
            "NO_FILES_ADMITTED_REFUSED",
            "capture has no admitted files",
        )
    return result
