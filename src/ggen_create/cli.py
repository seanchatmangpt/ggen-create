from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from .a2a import A2AService, serve as serve_a2a
from .agents import AgentRuntime
from .inspect import format_human, inspect_session
from .mcp import stdio_main
from .model import GgenCreateError, SESSION_FILE
from .package import build_package
from .runtime import ReceiptStore
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
from .skills import Broker, SkillRegistry
from .verify import compare_trees, verify_parity


def _find(project: str) -> Path:
    return find_session(Path.cwd(), project)


def _subject(project: str) -> tuple[Path, Path]:
    session = _find(project)
    return session, session.parent.resolve()


def _optional_subject(project: str) -> tuple[Path | None, Path]:
    try:
        session, root = _subject(project)
        return session, root
    except GgenCreateError as exc:
        if exc.code != "NO_SESSION_REFUSED":
            raise
        return None, Path.cwd().resolve()


def _json_arg(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GgenCreateError("JSON_ARGUMENT_REFUSED", str(exc)) from exc
    if not isinstance(value, dict):
        raise GgenCreateError(
            "JSON_ARGUMENT_REFUSED",
            "expected a JSON object",
        )
    return value


def _add_parity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--ggen-bin",
        default=os.environ.get("GGEN_BIN", "ggen"),
    )
    parser.add_argument("--set", dest="variation", required=True)
    parser.add_argument("--sync-arg", action="append", dest="sync_args")
    parser.add_argument("--check-command")
    parser.add_argument("--stdout-contains")
    parser.add_argument("--reference-dir")
    parser.add_argument("--reference-id")
    parser.add_argument("--force", action="store_true")


def _add_automatic_arguments(
    parser: argparse.ArgumentParser,
    *,
    confirmation: bool,
) -> None:
    parser.add_argument("--output", default="_ggen")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--variation")
    parser.add_argument(
        "--ggen-bin",
        default=os.environ.get("GGEN_BIN", "ggen"),
    )
    parser.add_argument("--force", action="store_true")
    if confirmation:
        parser.add_argument("--confirm", action="store_true")


def _add_autonomic_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", default="_ggen")
    parser.add_argument("--max-cycles", type=int, default=4)
    parser.add_argument("--stable-cycles", type=int, default=2)
    parser.add_argument("--interval", type=float, default=0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--variation")
    parser.add_argument(
        "--ggen-bin",
        default=os.environ.get("GGEN_BIN", "ggen"),
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="ggen-create",
        description="Create admitted ggen factories from working exemplars",
    )
    root.add_argument(
        "-p",
        "--project",
        default=SESSION_FILE,
        help="capture definition filename",
    )
    root.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable output",
    )
    sub = root.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("name")
    start.add_argument("--root", default=".")
    rename = sub.add_parser("rename")
    rename.add_argument("name")
    add = sub.add_parser("add")
    add.add_argument("paths", nargs="+")
    add.add_argument("-r", "--recursive", action="store_true")
    remove = sub.add_parser("remove", aliases=["rm"])
    remove.add_argument("paths", nargs="+")
    use = sub.add_parser("usename")
    use.add_argument("value")
    setopt = sub.add_parser("setopt")
    option_group = setopt.add_mutually_exclusive_group(required=True)
    option_group.add_argument("--gen-parent-dir", action="store_true")
    option_group.add_argument("--no-parent-dir", action="store_true")
    status = sub.add_parser("status", aliases=["s"])
    status.add_argument("files", nargs="*")
    status.add_argument("-v", "--verbose", action="store_true")
    generate = sub.add_parser("generate", aliases=["g"])
    generate.add_argument("--output", default="_ggen")
    generate.add_argument("--force", action="store_true")
    sub.add_parser("abort")

    verify = sub.add_parser("verify")
    _add_parity_arguments(verify)
    compare = sub.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")

    capture = sub.add_parser("capture")
    capture_sub = capture.add_subparsers(
        dest="capture_command",
        required=True,
    )
    capture_init = capture_sub.add_parser("init")
    capture_init.add_argument("name")
    capture_init.add_argument("--root", default=".")
    capture_include = capture_sub.add_parser("include")
    capture_include.add_argument("paths", nargs="+")
    capture_include.add_argument("-r", "--recursive", action="store_true")
    capture_remove = capture_sub.add_parser("remove")
    capture_remove.add_argument("paths", nargs="+")
    capture_sub.add_parser("abort")

    parameter = sub.add_parser("parameter")
    parameter_sub = parameter.add_subparsers(
        dest="parameter_command",
        required=True,
    )
    seed = parameter_sub.add_parser("seed")
    seed.add_argument("value")

    package = sub.add_parser("package")
    package_sub = package.add_subparsers(
        dest="package_command",
        required=True,
    )
    package_build = package_sub.add_parser("build")
    package_build.add_argument("--output", default="_ggen")
    package_build.add_argument("--force", action="store_true")
    package_build.add_argument("--confirm", action="store_true")
    package_verify = package_sub.add_parser("verify")
    package_verify.add_argument("--package")
    package_verify.add_argument("--output", default="_ggen")

    parity = sub.add_parser("parity")
    parity_sub = parity.add_subparsers(
        dest="parity_command",
        required=True,
    )
    parity_verify = parity_sub.add_parser("verify")
    _add_parity_arguments(parity_verify)
    parity_verify.add_argument("--confirm", action="store_true")
    parity_compare = parity_sub.add_parser("compare")
    parity_compare.add_argument("left")
    parity_compare.add_argument("right")

    automatic = sub.add_parser("automatic")
    automatic_sub = automatic.add_subparsers(
        dest="automatic_command",
        required=True,
    )
    automatic_plan_parser = automatic_sub.add_parser("plan")
    _add_automatic_arguments(
        automatic_plan_parser,
        confirmation=False,
    )
    automatic_run = automatic_sub.add_parser("run")
    _add_automatic_arguments(automatic_run, confirmation=True)
    automatic_watch = automatic_sub.add_parser("watch")
    _add_automatic_arguments(automatic_watch, confirmation=True)
    automatic_watch.add_argument("--cycles", type=int, default=2)
    automatic_watch.add_argument("--interval", type=float, default=0)

    autonomic = sub.add_parser("autonomic")
    autonomic_sub = autonomic.add_subparsers(
        dest="autonomic_command",
        required=True,
    )
    _add_autonomic_arguments(autonomic_sub.add_parser("cycle"))
    _add_autonomic_arguments(autonomic_sub.add_parser("run"))

    skills = sub.add_parser("skills")
    skills_sub = skills.add_subparsers(
        dest="skills_command",
        required=True,
    )
    skills_sub.add_parser("list")
    show = skills_sub.add_parser("show")
    show.add_argument("name")
    skill_plan = skills_sub.add_parser("plan")
    skill_plan.add_argument("name")
    skill_plan.add_argument("--arguments")
    skill_execute = skills_sub.add_parser("execute")
    skill_execute.add_argument("name")
    skill_execute.add_argument("--arguments")
    skill_execute.add_argument("--confirm", action="store_true")

    agents = sub.add_parser("agents")
    agents_sub = agents.add_subparsers(
        dest="agents_command",
        required=True,
    )
    agents_sub.add_parser("list")
    route = agents_sub.add_parser("route")
    route.add_argument("goal")
    route.add_argument("--context")
    agent_plan = agents_sub.add_parser("plan")
    agent_plan.add_argument("agent")
    agent_plan.add_argument("skill")
    agent_plan.add_argument("--arguments")
    dispatch = agents_sub.add_parser("dispatch")
    dispatch.add_argument("agent")
    dispatch.add_argument("skill")
    dispatch.add_argument("--arguments")
    dispatch.add_argument("--confirm", action="store_true")

    mcp = sub.add_parser("mcp")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_serve = mcp_sub.add_parser("serve")
    mcp_serve.add_argument("--root", default=".")

    a2a = sub.add_parser("a2a")
    a2a_sub = a2a.add_subparsers(dest="a2a_command", required=True)
    a2a_card = a2a_sub.add_parser("card")
    a2a_card.add_argument("--root", default=".")
    a2a_card.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
    )
    a2a_serve = a2a_sub.add_parser("serve")
    a2a_serve.add_argument("--root", default=".")
    a2a_serve.add_argument("--host", default="127.0.0.1")
    a2a_serve.add_argument("--port", type=int, default=8765)
    a2a_serve.add_argument("--base-url")

    selfplay = sub.add_parser("selfplay")
    selfplay_sub = selfplay.add_subparsers(
        dest="selfplay_command",
        required=True,
    )
    selfplay_run = selfplay_sub.add_parser("run")
    selfplay_run.add_argument(
        "--output",
        default=".ggen-create/selfplay",
    )
    selfplay_run.add_argument("--confirm", action="store_true")

    receipt = sub.add_parser("receipt")
    receipt_sub = receipt.add_subparsers(
        dest="receipt_command",
        required=True,
    )
    receipt_sub.add_parser("list")
    receipt_sub.add_parser("latest")
    receipt_verify = receipt_sub.add_parser("verify")
    receipt_verify.add_argument("path", nargs="?")
    receipt_sub.add_parser("chain")

    sub.add_parser("doctor")
    return root


def _print(value: object, as_json: bool) -> None:
    if as_json or not isinstance(value, str):
        print(
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    else:
        print(value)


def _verify_direct(
    args: argparse.Namespace,
    project: str,
) -> dict[str, Any]:
    return verify_parity(
        _find(project),
        output_root=Path(args.output),
        ggen_bin=args.ggen_bin,
        variation_value=args.variation,
        sync_args=args.sync_args or ["sync", "run"],
        behavior_command=args.check_command,
        stdout_contains=args.stdout_contains,
        reference_dir=(
            Path(args.reference_dir)
            if args.reference_dir
            else None
        ),
        reference_id=args.reference_id,
        force=args.force,
    )


def _broker_execute(
    project: str,
    name: str,
    arguments: dict[str, Any],
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    registry = SkillRegistry()
    skill = registry.get(name)
    if skill.requires_session:
        session, subject_root = _subject(project)
    else:
        session, subject_root = _optional_subject(project)
        session = None
    return Broker(subject_root).execute(
        registry.plan(name, arguments),
        session_path=session,
        confirm=confirm,
    )


def _autonomic_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "output_root": args.output,
        "max_cycles": args.max_cycles,
        "stable_cycles": args.stable_cycles,
        "interval_seconds": args.interval,
        "apply": args.apply,
        "verify": args.verify,
        "variation_value": args.variation,
        "ggen_bin": args.ggen_bin,
    }


def _agent_context(
    project: str,
    skill_name: str | None = None,
) -> tuple[Path | None, Path]:
    if skill_name is not None and SkillRegistry().get(skill_name).requires_session:
        session, root = _subject(project)
        return session, root
    session, root = _optional_subject(project)
    return None, root


def run(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = args.project
    as_json = args.json

    if args.command == "start":
        value: Any = {
            "session": str(
                start_session(Path(args.root), args.name, project)
            ),
            "standing": "PARTIAL_ALIVE",
        }
    elif args.command == "rename":
        rename_session(_find(project), args.name)
        value = f"renamed generator to {args.name}"
    elif args.command == "add":
        value = {
            "added": add_paths(
                _find(project),
                args.paths,
                recursive=args.recursive,
            )
        }
    elif args.command in {"remove", "rm"}:
        value = {"removed": remove_paths(_find(project), args.paths)}
    elif args.command == "usename":
        set_seed(_find(project), args.value)
        value = f"using '{args.value}' as templatization word"
    elif args.command == "setopt":
        set_parent_dir(
            _find(project),
            args.gen_parent_dir and not args.no_parent_dir,
        )
        value = "updated parent-dir generation"
    elif args.command in {"status", "s"}:
        report = inspect_session(_find(project))
        selected = set(args.files)
        report["files"] = [
            item
            for item in report["files"]
            if not selected or item["path"] in selected
        ]
        value = (
            report
            if as_json
            else format_human(report, verbose=args.verbose)
        )
    elif args.command in {"generate", "g"}:
        built = build_package(
            _find(project),
            Path(args.output),
            force=args.force,
        )
        value = {
            "package": str(built.package_dir),
            "changed": built.changed,
            "archived_previous": (
                str(built.archived_previous)
                if built.archived_previous
                else None
            ),
            "receipt": str(built.receipt_path),
        }
    elif args.command == "abort":
        abort_session(_find(project))
        value = "capture aborted"
    elif args.command == "verify":
        value = _verify_direct(args, project)
    elif args.command == "compare":
        value = compare_trees(Path(args.left), Path(args.right))
        _print(value, as_json)
        return 0 if value["equal"] else 1
    elif args.command == "capture":
        if args.capture_command == "init":
            value = {
                "session": str(
                    start_session(
                        Path(args.root),
                        args.name,
                        project,
                    )
                )
            }
        elif args.capture_command == "include":
            value = {
                "added": add_paths(
                    _find(project),
                    args.paths,
                    recursive=args.recursive,
                )
            }
        elif args.capture_command == "remove":
            value = {
                "removed": remove_paths(
                    _find(project),
                    args.paths,
                )
            }
        else:
            abort_session(_find(project))
            value = "capture aborted"
    elif args.command == "parameter":
        set_seed(_find(project), args.value)
        value = {"seed": args.value}
    elif args.command == "package":
        if args.package_command == "build":
            value = _broker_execute(
                project,
                "package.build",
                {
                    "output_root": args.output,
                    "force": args.force,
                },
                confirm=args.confirm,
            )
        else:
            arguments = {"output_root": args.output}
            if args.package:
                arguments["package"] = args.package
            value = _broker_execute(
                project,
                "package.verify",
                arguments,
            )
    elif args.command == "parity":
        if args.parity_command == "compare":
            value = compare_trees(Path(args.left), Path(args.right))
            _print(value, as_json)
            return 0 if value["equal"] else 1
        value = _broker_execute(
            project,
            "parity.verify",
            {
                "output_root": args.output,
                "ggen_bin": args.ggen_bin,
                "variation_value": args.variation,
                "sync_args": args.sync_args or ["sync", "run"],
                "reference_dir": args.reference_dir,
                "reference_id": args.reference_id,
                "force": args.force,
            },
            confirm=args.confirm,
        )
    elif args.command == "automatic":
        if args.automatic_command == "plan":
            value = _broker_execute(
                project,
                "automatic.plan",
                {
                    "output_root": args.output,
                    "verify": args.verify,
                    "variation_value": args.variation,
                },
            )
        elif args.automatic_command == "run":
            value = _broker_execute(
                project,
                "automatic.create",
                {
                    "output_root": args.output,
                    "verify": args.verify,
                    "variation_value": args.variation,
                    "ggen_bin": args.ggen_bin,
                    "force": args.force,
                },
                confirm=args.confirm,
            )
        else:
            value = _broker_execute(
                project,
                "automatic.watch",
                {
                    "output_root": args.output,
                    "cycles": args.cycles,
                    "interval_seconds": args.interval,
                    "verify": args.verify,
                    "variation_value": args.variation,
                    "ggen_bin": args.ggen_bin,
                    "force": args.force,
                },
                confirm=args.confirm,
            )
    elif args.command == "autonomic":
        value = _broker_execute(
            project,
            (
                "autonomic.cycle"
                if args.autonomic_command == "cycle"
                else "autonomic.run"
            ),
            _autonomic_arguments(args),
            confirm=args.confirm,
        )
    elif args.command == "skills":
        registry = SkillRegistry()
        if args.skills_command == "list":
            value = registry.list()
        elif args.skills_command == "show":
            value = registry.get(args.name).to_dict()
        elif args.skills_command == "plan":
            value = registry.plan(
                args.name,
                _json_arg(args.arguments),
            ).to_dict()
        else:
            value = _broker_execute(
                project,
                args.name,
                _json_arg(args.arguments),
                confirm=args.confirm,
            )
    elif args.command == "agents":
        skill_name = (
            args.skill
            if args.agents_command == "dispatch"
            else None
        )
        session, subject_root = _agent_context(project, skill_name)
        runtime = AgentRuntime(subject_root)
        if args.agents_command == "list":
            value = runtime.list()
        elif args.agents_command == "route":
            value = runtime.route(
                args.goal,
                _json_arg(args.context),
            )
        elif args.agents_command == "plan":
            value = runtime.plan(
                args.agent,
                args.skill,
                _json_arg(args.arguments),
            )
        else:
            value = runtime.dispatch(
                args.agent,
                args.skill,
                _json_arg(args.arguments),
                session_path=session,
                confirm=args.confirm,
            )
    elif args.command == "mcp":
        return stdio_main(Path(args.root))
    elif args.command == "a2a":
        if args.a2a_command == "card":
            value = A2AService(
                Path(args.root),
                base_url=args.base_url,
            ).agent_card()
        else:
            serve_a2a(
                Path(args.root),
                host=args.host,
                port=args.port,
                base_url=args.base_url,
            )
            return 0
    elif args.command == "selfplay":
        value = _broker_execute(
            project,
            "selfplay.run",
            {"output_root": args.output},
            confirm=args.confirm,
        )
    elif args.command == "receipt":
        _, subject_root = _optional_subject(project)
        store = ReceiptStore(subject_root)
        if args.receipt_command == "list":
            value = store.list()
        elif args.receipt_command == "latest":
            value = store.latest()
        elif args.receipt_command == "chain":
            value = _broker_execute(
                project,
                "receipt.chain.verify",
                {},
            )
        else:
            value = _broker_execute(
                project,
                "receipt.verify",
                {"path": args.path},
            )
    elif args.command == "doctor":
        value = _broker_execute(
            project,
            "doctor.inspect",
            {"project": project},
        )["result"]
    else:
        raise GgenCreateError(
            "COMMAND_NOT_IMPLEMENTED_REFUSED",
            str(args.command),
        )

    _print(value, as_json)
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    try:
        raise SystemExit(run(argv))
    except GgenCreateError as exc:
        print(f"ggen-create - {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
