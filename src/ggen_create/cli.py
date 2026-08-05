from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from .a2a import A2AService, serve as serve_a2a
from .agents import AgentRuntime
from .automatic import automatic_plan, run_automatic, watch_automatic
from .autonomic import AutonomicPolicy, autonomic_cycle, run_autonomic
from .inspect import format_human, inspect_session
from .mcp import stdio_main
from .model import GgenCreateError, SESSION_FILE
from .package import build_package
from .runtime import ReceiptStore
from .selfplay import run_selfplay
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


def _json_arg(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GgenCreateError("JSON_ARGUMENT_REFUSED", str(exc)) from exc
    if not isinstance(value, dict):
        raise GgenCreateError("JSON_ARGUMENT_REFUSED", "expected a JSON object")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ggen-create", description="Create admitted ggen factories from working exemplars")
    root.add_argument("-p", "--project", default=SESSION_FILE, help="capture definition filename")
    root.add_argument("--json", action="store_true", help="emit machine-readable output")
    sub = root.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start"); start.add_argument("name"); start.add_argument("--root", default=".")
    rename = sub.add_parser("rename"); rename.add_argument("name")
    add = sub.add_parser("add"); add.add_argument("paths", nargs="+"); add.add_argument("-r", "--recursive", action="store_true")
    remove = sub.add_parser("remove", aliases=["rm"]); remove.add_argument("paths", nargs="+")
    use = sub.add_parser("usename"); use.add_argument("value")
    setopt = sub.add_parser("setopt"); group = setopt.add_mutually_exclusive_group(required=True); group.add_argument("--gen-parent-dir", action="store_true"); group.add_argument("--no-parent-dir", action="store_true")
    status = sub.add_parser("status", aliases=["s"]); status.add_argument("files", nargs="*"); status.add_argument("-v", "--verbose", action="store_true")
    generate = sub.add_parser("generate", aliases=["g"]); generate.add_argument("--output", default="_ggen"); generate.add_argument("--force", action="store_true")
    sub.add_parser("abort")

    verify = sub.add_parser("verify")
    verify.add_argument("--output", required=True)
    verify.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen"))
    verify.add_argument("--set", dest="variation", required=True)
    verify.add_argument("--sync-arg", action="append", dest="sync_args")
    verify.add_argument("--check-command"); verify.add_argument("--stdout-contains")
    verify.add_argument("--reference-dir"); verify.add_argument("--reference-id")
    verify.add_argument("--force", action="store_true")
    compare = sub.add_parser("compare"); compare.add_argument("left"); compare.add_argument("right")

    capture = sub.add_parser("capture"); capture_sub = capture.add_subparsers(dest="capture_command", required=True)
    capture_init = capture_sub.add_parser("init"); capture_init.add_argument("name"); capture_init.add_argument("--root", default=".")
    capture_include = capture_sub.add_parser("include"); capture_include.add_argument("paths", nargs="+"); capture_include.add_argument("-r", "--recursive", action="store_true")
    capture_remove = capture_sub.add_parser("remove"); capture_remove.add_argument("paths", nargs="+")
    capture_sub.add_parser("abort")
    parameter = sub.add_parser("parameter"); parameter_sub = parameter.add_subparsers(dest="parameter_command", required=True); seed = parameter_sub.add_parser("seed"); seed.add_argument("value")
    package = sub.add_parser("package"); package_sub = package.add_subparsers(dest="package_command", required=True); package_build = package_sub.add_parser("build"); package_build.add_argument("--output", default="_ggen"); package_build.add_argument("--force", action="store_true")
    parity = sub.add_parser("parity"); parity_sub = parity.add_subparsers(dest="parity_command", required=True)
    parity_verify = parity_sub.add_parser("verify")
    parity_verify.add_argument("--output", required=True); parity_verify.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen")); parity_verify.add_argument("--set", dest="variation", required=True); parity_verify.add_argument("--sync-arg", action="append", dest="sync_args"); parity_verify.add_argument("--check-command"); parity_verify.add_argument("--stdout-contains"); parity_verify.add_argument("--reference-dir"); parity_verify.add_argument("--reference-id"); parity_verify.add_argument("--force", action="store_true")
    parity_compare = parity_sub.add_parser("compare"); parity_compare.add_argument("left"); parity_compare.add_argument("right")

    automatic = sub.add_parser("automatic"); automatic_sub = automatic.add_subparsers(dest="automatic_command", required=True)
    automatic_plan_parser = automatic_sub.add_parser("plan"); automatic_plan_parser.add_argument("--output", default="_ggen"); automatic_plan_parser.add_argument("--verify", action="store_true"); automatic_plan_parser.add_argument("--variation")
    automatic_run = automatic_sub.add_parser("run"); automatic_run.add_argument("--output", default="_ggen"); automatic_run.add_argument("--confirm", action="store_true"); automatic_run.add_argument("--verify", action="store_true"); automatic_run.add_argument("--variation"); automatic_run.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen")); automatic_run.add_argument("--force", action="store_true")
    automatic_watch = automatic_sub.add_parser("watch"); automatic_watch.add_argument("--output", default="_ggen"); automatic_watch.add_argument("--cycles", type=int, default=2); automatic_watch.add_argument("--interval", type=float, default=0); automatic_watch.add_argument("--confirm", action="store_true"); automatic_watch.add_argument("--verify", action="store_true"); automatic_watch.add_argument("--variation"); automatic_watch.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen"))

    autonomic = sub.add_parser("autonomic"); autonomic_sub = autonomic.add_subparsers(dest="autonomic_command", required=True)
    for name in ("cycle", "run"):
        item = autonomic_sub.add_parser(name); item.add_argument("--output", default="_ggen"); item.add_argument("--max-cycles", type=int, default=4); item.add_argument("--stable-cycles", type=int, default=2); item.add_argument("--interval", type=float, default=0); item.add_argument("--apply", action="store_true"); item.add_argument("--confirm", action="store_true"); item.add_argument("--verify", action="store_true"); item.add_argument("--variation"); item.add_argument("--ggen-bin", default=os.environ.get("GGEN_BIN", "ggen"))

    skills = sub.add_parser("skills"); skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skills_sub.add_parser("list"); show = skills_sub.add_parser("show"); show.add_argument("name")
    skill_plan = skills_sub.add_parser("plan"); skill_plan.add_argument("name"); skill_plan.add_argument("--arguments")
    skill_execute = skills_sub.add_parser("execute"); skill_execute.add_argument("name"); skill_execute.add_argument("--arguments"); skill_execute.add_argument("--confirm", action="store_true")

    agents = sub.add_parser("agents"); agents_sub = agents.add_subparsers(dest="agents_command", required=True)
    agents_sub.add_parser("list"); route = agents_sub.add_parser("route"); route.add_argument("goal"); route.add_argument("--context")
    agent_plan = agents_sub.add_parser("plan"); agent_plan.add_argument("agent"); agent_plan.add_argument("skill"); agent_plan.add_argument("--arguments")
    dispatch = agents_sub.add_parser("dispatch"); dispatch.add_argument("agent"); dispatch.add_argument("skill"); dispatch.add_argument("--arguments"); dispatch.add_argument("--confirm", action="store_true")

    mcp = sub.add_parser("mcp"); mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True); mcp_serve = mcp_sub.add_parser("serve"); mcp_serve.add_argument("--root", default=".")
    a2a = sub.add_parser("a2a"); a2a_sub = a2a.add_subparsers(dest="a2a_command", required=True)
    a2a_card = a2a_sub.add_parser("card"); a2a_card.add_argument("--root", default="."); a2a_card.add_argument("--base-url", default="http://127.0.0.1:8765")
    a2a_serve = a2a_sub.add_parser("serve"); a2a_serve.add_argument("--root", default="."); a2a_serve.add_argument("--host", default="127.0.0.1"); a2a_serve.add_argument("--port", type=int, default=8765); a2a_serve.add_argument("--base-url")
    selfplay = sub.add_parser("selfplay"); selfplay_sub = selfplay.add_subparsers(dest="selfplay_command", required=True); selfplay_run = selfplay_sub.add_parser("run"); selfplay_run.add_argument("--output", default=".ggen-create/selfplay"); selfplay_run.add_argument("--confirm", action="store_true")
    receipt = sub.add_parser("receipt"); receipt_sub = receipt.add_subparsers(dest="receipt_command", required=True); receipt_sub.add_parser("list"); receipt_sub.add_parser("latest"); receipt_verify = receipt_sub.add_parser("verify"); receipt_verify.add_argument("path", nargs="?")
    sub.add_parser("doctor")
    return root


def _print(value: object, as_json: bool) -> None:
    if as_json or not isinstance(value, str):
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        print(value)


def _verify(args: argparse.Namespace, project: str) -> dict[str, Any]:
    return verify_parity(_find(project), output_root=Path(args.output), ggen_bin=args.ggen_bin, variation_value=args.variation, sync_args=args.sync_args or ["sync", "run"], behavior_command=args.check_command, stdout_contains=args.stdout_contains, reference_dir=Path(args.reference_dir) if args.reference_dir else None, reference_id=args.reference_id, force=args.force)


def _policy(args: argparse.Namespace) -> AutonomicPolicy:
    return AutonomicPolicy(max_cycles=args.max_cycles, stable_cycles=args.stable_cycles, interval_seconds=args.interval, apply=args.apply, confirm=args.confirm, verify=args.verify, variation_value=args.variation, ggen_bin=args.ggen_bin)


def run(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv); project = args.project; as_json = args.json
    if args.command == "start":
        _print({"session": str(start_session(Path(args.root), args.name, project)), "standing": "PARTIAL_ALIVE"}, as_json)
    elif args.command == "rename": rename_session(_find(project), args.name); _print(f"renamed generator to {args.name}", as_json)
    elif args.command == "add": _print({"added": add_paths(_find(project), args.paths, recursive=args.recursive)}, as_json)
    elif args.command in {"remove", "rm"}: _print({"removed": remove_paths(_find(project), args.paths)}, as_json)
    elif args.command == "usename": set_seed(_find(project), args.value); _print(f"using '{args.value}' as templatization word", as_json)
    elif args.command == "setopt": set_parent_dir(_find(project), args.gen_parent_dir and not args.no_parent_dir); _print("updated parent-dir generation", as_json)
    elif args.command in {"status", "s"}:
        report = inspect_session(_find(project)); selected = set(args.files); report["files"] = [item for item in report["files"] if not selected or item["path"] in selected]; _print(report if as_json else format_human(report, verbose=args.verbose), as_json)
    elif args.command in {"generate", "g"}:
        value = build_package(_find(project), Path(args.output), force=args.force); _print({"package": str(value.package_dir), "changed": value.changed, "archived_previous": str(value.archived_previous) if value.archived_previous else None, "receipt": str(value.receipt_path)}, as_json)
    elif args.command == "abort": abort_session(_find(project)); _print("capture aborted", as_json)
    elif args.command == "verify": _print(_verify(args, project), as_json)
    elif args.command == "compare":
        value = compare_trees(Path(args.left), Path(args.right)); _print(value, as_json); return 0 if value["equal"] else 1
    elif args.command == "capture":
        if args.capture_command == "init": _print({"session": str(start_session(Path(args.root), args.name, project))}, as_json)
        elif args.capture_command == "include": _print({"added": add_paths(_find(project), args.paths, recursive=args.recursive)}, as_json)
        elif args.capture_command == "remove": _print({"removed": remove_paths(_find(project), args.paths)}, as_json)
        else: abort_session(_find(project)); _print("capture aborted", as_json)
    elif args.command == "parameter": set_seed(_find(project), args.value); _print({"seed": args.value}, as_json)
    elif args.command == "package":
        value = build_package(_find(project), Path(args.output), force=args.force); _print({"package": str(value.package_dir), "changed": value.changed}, as_json)
    elif args.command == "parity":
        if args.parity_command == "verify": _print(_verify(args, project), as_json)
        else:
            value = compare_trees(Path(args.left), Path(args.right)); _print(value, as_json); return 0 if value["equal"] else 1
    elif args.command == "automatic":
        session = _find(project)
        if args.automatic_command == "plan": _print(automatic_plan(session, output_root=Path(args.output), variation_value=args.variation, verify=args.verify), as_json)
        elif args.automatic_command == "run": _print(run_automatic(session, output_root=Path(args.output), apply=True, confirm=args.confirm, verify=args.verify, variation_value=args.variation, ggen_bin=args.ggen_bin, force=args.force), as_json)
        else: _print(watch_automatic(session, output_root=Path(args.output), cycles=args.cycles, interval_seconds=args.interval, confirm=args.confirm, verify=args.verify, variation_value=args.variation, ggen_bin=args.ggen_bin), as_json)
    elif args.command == "autonomic":
        value = autonomic_cycle(_find(project), output_root=Path(args.output), policy=_policy(args)) if args.autonomic_command == "cycle" else run_autonomic(_find(project), output_root=Path(args.output), policy=_policy(args)); _print(value, as_json)
    elif args.command == "skills":
        registry = SkillRegistry()
        if args.skills_command == "list": value = registry.list()
        elif args.skills_command == "show": value = registry.get(args.name).to_dict()
        elif args.skills_command == "plan": value = registry.plan(args.name, _json_arg(args.arguments)).to_dict()
        else: value = Broker(Path.cwd()).execute(registry.plan(args.name, _json_arg(args.arguments)), session_path=_find(project), confirm=args.confirm)
        _print(value, as_json)
    elif args.command == "agents":
        runtime = AgentRuntime(Path.cwd())
        if args.agents_command == "list": value = runtime.list()
        elif args.agents_command == "route": value = runtime.route(args.goal, _json_arg(args.context))
        elif args.agents_command == "plan": value = runtime.plan(args.agent, args.skill, _json_arg(args.arguments))
        else: value = runtime.dispatch(args.agent, args.skill, _json_arg(args.arguments), session_path=_find(project), confirm=args.confirm)
        _print(value, as_json)
    elif args.command == "mcp": return stdio_main(Path(args.root))
    elif args.command == "a2a":
        if args.a2a_command == "card": _print(A2AService(Path(args.root), base_url=args.base_url).agent_card(), True)
        else: serve_a2a(Path(args.root), host=args.host, port=args.port, base_url=args.base_url)
    elif args.command == "selfplay":
        if not args.confirm: raise GgenCreateError("ACTUATION_CONFIRMATION_REQUIRED_REFUSED", "selfplay requires --confirm")
        _print(run_selfplay(_find(project), output_root=Path(args.output)), as_json)
    elif args.command == "receipt":
        store = ReceiptStore(Path.cwd())
        if args.receipt_command == "list": value = store.list()
        elif args.receipt_command == "latest": value = store.latest()
        else:
            path = Path(args.path) if args.path else Path((store.latest() or {}).get("path", "")); value = ReceiptStore.verify(path) if str(path) else None
        _print(value, as_json)
    elif args.command == "doctor":
        _print({"state": "ALIVE", "automatic": True, "autonomic": True, "mcp": {"protocolVersion": "2025-11-25", "transport": "stdio"}, "a2a": {"protocolVersion": "1.0", "transport": "loopback-http"}, "skills": len(SkillRegistry().list()), "agents": len(AgentRuntime(Path.cwd()).list()), "actuation": "broker-only-confirmed"}, as_json)
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    try:
        raise SystemExit(run(argv))
    except GgenCreateError as exc:
        print(f"ggen-create - {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
