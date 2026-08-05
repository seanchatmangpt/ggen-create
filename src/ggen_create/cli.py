from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from .inspect import format_human, inspect_session
from .model import GgenCreateError, SESSION_FILE
from .package import build_package
from .session import (
    abort_session,
    add_paths,
    find_session,
    remove_paths,
    rename_session,
    set_parent_dir,
    set_seed,
    start_session,
)
from .verify import compare_trees, verify_parity


def _find(project: str) -> Path:
    return find_session(Path.cwd(), project)


def _add_common_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p", "--project", default=SESSION_FILE, help="capture definition filename"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="ggen-create",
        description="Create admitted ggen packages from working exemplars",
    )
    _add_common_project(root)
    root.add_argument("--json", action="store_true", help="emit machine-readable output")
    sub = root.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start a capture session")
    start.add_argument("name")
    start.add_argument("--root", default=".")

    rename = sub.add_parser("rename", help="rename the target generator")
    rename.add_argument("name")

    add = sub.add_parser("add", help="admit files or directories")
    add.add_argument("paths", nargs="+")
    add.add_argument("-r", "--recursive", action="store_true")

    remove = sub.add_parser("remove", aliases=["rm"], help="remove admitted paths")
    remove.add_argument("paths", nargs="+")

    use = sub.add_parser("usename", help="seed the name parameter")
    use.add_argument("value")

    setopt = sub.add_parser("setopt", help="configure generator options")
    group = setopt.add_mutually_exclusive_group(required=True)
    group.add_argument("--gen-parent-dir", action="store_true")
    group.add_argument("--no-parent-dir", action="store_true")

    status = sub.add_parser("status", aliases=["s"], help="inspect replacements")
    status.add_argument("files", nargs="*")
    status.add_argument("-v", "--verbose", action="store_true")

    generate = sub.add_parser("generate", aliases=["g"], help="build a ggen package")
    generate.add_argument("--output", default="_ggen")
    generate.add_argument("--force", action="store_true")

    abort = sub.add_parser("abort", help="delete the active capture session")
    abort.set_defaults(_abort=True)

    verify = sub.add_parser("verify", help="execute reconstruction and variation parity")
    verify.add_argument("--output", required=True)
    verify.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen"))
    verify.add_argument("--set", dest="variation", required=True)
    verify.add_argument(
        "--sync-arg",
        action="append",
        dest="sync_args",
        help="repeat to replace the default 'sync run' arguments",
    )
    verify.add_argument("--check-command")
    verify.add_argument("--stdout-contains")
    verify.add_argument("--reference-dir")
    verify.add_argument("--reference-id")
    verify.add_argument("--force", action="store_true")

    compare = sub.add_parser("compare", help="compare two artifact trees byte-for-byte")
    compare.add_argument("left")
    compare.add_argument("right")

    # Native spelling aliases. They route to the same deterministic parity skills.
    capture = sub.add_parser("capture", help="capture-session operations")
    capture_sub = capture.add_subparsers(dest="capture_command", required=True)
    capture_init = capture_sub.add_parser("init")
    capture_init.add_argument("name")
    capture_init.add_argument("--root", default=".")
    capture_include = capture_sub.add_parser("include")
    capture_include.add_argument("paths", nargs="+")
    capture_include.add_argument("-r", "--recursive", action="store_true")
    capture_remove = capture_sub.add_parser("remove")
    capture_remove.add_argument("paths", nargs="+")
    capture_sub.add_parser("abort")

    parameter = sub.add_parser("parameter", help="parameter-hypothesis operations")
    parameter_sub = parameter.add_subparsers(dest="parameter_command", required=True)
    seed = parameter_sub.add_parser("seed")
    seed.add_argument("value")

    package = sub.add_parser("package", help="ggen-package operations")
    package_sub = package.add_subparsers(dest="package_command", required=True)
    build = package_sub.add_parser("build")
    build.add_argument("--output", default="_ggen")
    build.add_argument("--force", action="store_true")

    parity = sub.add_parser("parity", help="parity checkpoint operations")
    parity_sub = parity.add_subparsers(dest="parity_command", required=True)
    parity_verify = parity_sub.add_parser("verify")
    parity_verify.add_argument("--output", required=True)
    parity_verify.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen"))
    parity_verify.add_argument("--set", dest="variation", required=True)
    parity_verify.add_argument("--sync-arg", action="append", dest="sync_args")
    parity_verify.add_argument("--check-command")
    parity_verify.add_argument("--stdout-contains")
    parity_verify.add_argument("--reference-dir")
    parity_verify.add_argument("--reference-id")
    parity_verify.add_argument("--force", action="store_true")
    parity_compare = parity_sub.add_parser("compare")
    parity_compare.add_argument("left")
    parity_compare.add_argument("right")
    return root


def _print(value: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    elif isinstance(value, str):
        print(value)
    else:
        print(value)


def _verify_from_args(args: argparse.Namespace, project: str) -> dict[str, object]:
    sync_args = args.sync_args if args.sync_args else ["sync", "run"]
    return verify_parity(
        _find(project),
        output_root=Path(args.output),
        ggen_bin=args.ggen_bin,
        variation_value=args.variation,
        sync_args=sync_args,
        behavior_command=args.check_command,
        stdout_contains=args.stdout_contains,
        reference_dir=Path(args.reference_dir) if args.reference_dir else None,
        reference_id=args.reference_id,
        force=args.force,
    )


def run(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = args.project
    as_json = args.json

    if args.command == "start":
        path = start_session(Path(args.root), args.name, project)
        _print({"session": str(path), "standing": "PARTIAL_ALIVE"}, as_json)
    elif args.command == "rename":
        rename_session(_find(project), args.name)
        _print(f"renamed generator to {args.name}", as_json)
    elif args.command == "add":
        added = add_paths(_find(project), args.paths, recursive=args.recursive)
        _print({"added": added}, as_json)
    elif args.command in {"remove", "rm"}:
        removed = remove_paths(_find(project), args.paths)
        _print({"removed": removed}, as_json)
    elif args.command == "usename":
        set_seed(_find(project), args.value)
        _print(f"using '{args.value}' as templatization word", as_json)
    elif args.command == "setopt":
        set_parent_dir(_find(project), args.gen_parent_dir and not args.no_parent_dir)
        _print("updated parent-dir generation", as_json)
    elif args.command in {"status", "s"}:
        report = inspect_session(_find(project))
        if args.files:
            selected = set(args.files)
            report["files"] = [item for item in report["files"] if item["path"] in selected]
        _print(report if as_json else format_human(report, verbose=args.verbose), as_json)
    elif args.command in {"generate", "g"}:
        result = build_package(_find(project), Path(args.output), force=args.force)
        _print(
            {
                "package": str(result.package_dir),
                "changed": result.changed,
                "archived_previous": str(result.archived_previous)
                if result.archived_previous
                else None,
                "receipt": str(result.receipt_path),
            },
            as_json,
        )
    elif args.command == "abort":
        abort_session(_find(project))
        _print("capture aborted", as_json)
    elif args.command == "verify":
        _print(_verify_from_args(args, project), as_json)
    elif args.command == "compare":
        result = compare_trees(Path(args.left), Path(args.right))
        _print(result, as_json)
        return 0 if result["equal"] else 1
    elif args.command == "capture":
        if args.capture_command == "init":
            path = start_session(Path(args.root), args.name, project)
            _print({"session": str(path)}, as_json)
        elif args.capture_command == "include":
            _print(
                {
                    "added": add_paths(
                        _find(project), args.paths, recursive=args.recursive
                    )
                },
                as_json,
            )
        elif args.capture_command == "remove":
            _print({"removed": remove_paths(_find(project), args.paths)}, as_json)
        elif args.capture_command == "abort":
            abort_session(_find(project))
            _print("capture aborted", as_json)
    elif args.command == "parameter" and args.parameter_command == "seed":
        set_seed(_find(project), args.value)
        _print({"seed": args.value}, as_json)
    elif args.command == "package" and args.package_command == "build":
        result = build_package(_find(project), Path(args.output), force=args.force)
        _print({"package": str(result.package_dir), "changed": result.changed}, as_json)
    elif args.command == "parity":
        if args.parity_command == "verify":
            _print(_verify_from_args(args, project), as_json)
        elif args.parity_command == "compare":
            result = compare_trees(Path(args.left), Path(args.right))
            _print(result, as_json)
            return 0 if result["equal"] else 1
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    try:
        raise SystemExit(run(argv))
    except GgenCreateError as exc:
        print(f"ggen-create - {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
