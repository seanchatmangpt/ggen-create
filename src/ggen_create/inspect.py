from __future__ import annotations

from pathlib import Path
from typing import Any

from .cases import parameterize_body, parameterize_path
from .model import GgenCreateError
from .session import admitted_files, load_session


def inspect_session(session_path: Path) -> dict[str, Any]:
    session = load_session(session_path)
    seed = session["templatize_using_name"]
    if not seed:
        raise GgenCreateError(
            "PARAMETER_NOT_SEEDED_REFUSED", "run 'ggen-create usename <value>'"
        )

    root = session_path.parent
    files: list[dict[str, Any]] = []
    total = 0
    for rel in admitted_files(session_path):
        source = (root / rel).read_text(encoding="utf-8")
        target_template, path_replacements = parameterize_path(rel, seed)
        _, content_replacements = parameterize_body(source, seed)
        count = len(path_replacements) + len(content_replacements)
        total += count
        files.append(
            {
                "path": rel,
                "target_template": target_template,
                "path_replacements": [item.to_json() for item in path_replacements],
                "content_replacements": [item.to_json() for item in content_replacements],
                "replacement_count": count,
            }
        )
    return {
        "generator": session["name"],
        "session": str(session_path),
        "seed": seed,
        "gen_parent_dir": session["gen_parent_dir"],
        "file_count": len(files),
        "replacement_count": total,
        "files": files,
    }


def format_human(report: dict[str, Any], *, verbose: bool = False) -> str:
    lines = [
        f"Using the string \"{report['seed']}\" to templatize files",
        "",
        "The following files are included in the generator:",
    ]
    for file_info in report["files"]:
        lines.append(
            f"[included] - {file_info['path']} "
            f"[{file_info['replacement_count']} replacements] -> "
            f"{file_info['target_template']}"
        )
        if verbose:
            for replacement in file_info["path_replacements"]:
                lines.append(
                    "  path: "
                    f"{replacement['old_text']} -> {{{{ row.{replacement['variable']} }}}}"
                )
            for replacement in file_info["content_replacements"]:
                lines.append(
                    "  content: "
                    f"{replacement['old_text']} -> {{{{ row.{replacement['variable']} }}}}"
                )
    lines.extend(
        [
            "",
            f"Total replacements: {report['replacement_count']}",
            "Parent dir generation: "
            + ("ON" if report["gen_parent_dir"] else "OFF"),
        ]
    )
    return "\n".join(lines)
