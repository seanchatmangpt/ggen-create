"""FastMCP server for ggen-create."""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from fastmcp.utilities.tasks import TaskConfig
from mcp.types import ToolAnnotations

from .mcp_services import McpService
from .model import APP_VERSION, GgenCreateError, SESSION_FILE

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "ggen-create-mcp"
SERVER_VERSION = APP_VERSION
RELATED_TASK_KEY = "io.modelcontextprotocol/related-task"
SERVER_INSTRUCTIONS = (
    "Inspect and plan first. Every write tool requires confirm:true. "
    "The Broker is the only native DO boundary."
)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)
_TASK_OPTIONAL = TaskConfig(mode="optional", poll_interval=timedelta(milliseconds=250))


def _unwrap(result: ToolResult) -> ToolResult | dict[str, Any]:
    if result.is_error:
        return result
    return result.structured_content or {}


def create_mcp_server(root: Path) -> FastMCP:
    service = McpService(root)
    mcp = FastMCP(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=SERVER_INSTRUCTIONS,
    )

    @mcp.tool(
        name="ggen_create_status",
        title="Inspect capture",
        description="Read admitted correspondence state.",
        annotations=_READ_ONLY,
    )
    def ggen_create_status(project: str = SESSION_FILE) -> dict[str, Any]:
        return _unwrap(service.execute_named("ggen_create_status", {"project": project}))

    @mcp.tool(
        name="ggen_create_automatic_plan",
        title="Plan automatic creation",
        description="Plan package manufacture without writing.",
        annotations=_READ_ONLY,
    )
    def ggen_create_automatic_plan(
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        verify: bool = False,
        variation_value: str | None = None,
    ) -> dict[str, Any]:
        return _unwrap(
            service.execute_named(
                "ggen_create_automatic_plan",
                {
                    "project": project,
                    "output_root": output_root,
                    "verify": verify,
                    "variation_value": variation_value,
                },
            )
        )

    @mcp.tool(
        name="ggen_create_package_verify",
        title="Verify package integrity",
        description="Compare a package byte-for-byte with its package receipt.",
        annotations=_READ_ONLY,
    )
    def ggen_create_package_verify(
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        package: str | None = None,
    ) -> dict[str, Any]:
        return _unwrap(
            service.execute_named(
                "ggen_create_package_verify",
                {
                    "project": project,
                    "output_root": output_root,
                    "package": package,
                },
            )
        )

    @mcp.tool(
        name="ggen_create_apply",
        title="Apply automatic creation",
        description="Manufacture a deterministic ggen package.",
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_apply(
        confirm: bool,
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        verify: bool = False,
        variation_value: str | None = None,
        ggen_bin: str = "ggen",
        force: bool = False,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_apply",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
                "verify": verify,
                "variation_value": variation_value,
                "ggen_bin": ggen_bin,
                "force": force,
            },
        )

    @mcp.tool(
        name="ggen_create_automatic_watch",
        title="Watch and reconcile",
        description="Observe bounded fingerprint and package-integrity drift.",
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_automatic_watch(
        confirm: bool,
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        verify: bool = False,
        variation_value: str | None = None,
        ggen_bin: str = "ggen",
        cycles: int = 2,
        interval_seconds: float = 0,
        force: bool = False,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_automatic_watch",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
                "verify": verify,
                "variation_value": variation_value,
                "ggen_bin": ggen_bin,
                "cycles": cycles,
                "interval_seconds": interval_seconds,
                "force": force,
            },
        )

    @mcp.tool(
        name="ggen_create_autonomic_cycle",
        title="Run autonomic cycle",
        description="Execute one bounded MAPE-K cycle.",
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_autonomic_cycle(
        confirm: bool,
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        verify: bool = False,
        variation_value: str | None = None,
        ggen_bin: str = "ggen",
        apply: bool = True,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_autonomic_cycle",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
                "verify": verify,
                "variation_value": variation_value,
                "ggen_bin": ggen_bin,
                "apply": apply,
            },
        )

    @mcp.tool(
        name="ggen_create_autonomic_run",
        title="Run autonomic convergence",
        description="Run bounded MAPE-K convergence with a cycle ceiling.",
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_autonomic_run(
        confirm: bool,
        project: str = SESSION_FILE,
        output_root: str = "_ggen",
        verify: bool = False,
        variation_value: str | None = None,
        ggen_bin: str = "ggen",
        max_cycles: int = 4,
        stable_cycles: int = 2,
        interval_seconds: float = 0,
        apply: bool = True,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_autonomic_run",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
                "verify": verify,
                "variation_value": variation_value,
                "ggen_bin": ggen_bin,
                "max_cycles": max_cycles,
                "stable_cycles": stable_cycles,
                "interval_seconds": interval_seconds,
                "apply": apply,
            },
        )

    @mcp.tool(
        name="ggen_create_agent_route",
        title="Route goal",
        description="Route a goal deterministically to a bounded agent and skill.",
        annotations=_READ_ONLY,
    )
    def ggen_create_agent_route(
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _unwrap(
            service.execute_named(
                "ggen_create_agent_route",
                {"goal": goal, "context": context or {}},
            )
        )

    @mcp.tool(
        name="ggen_create_agent_dispatch",
        title="Dispatch agent",
        description="Submit an authorized skill intent through the Broker.",
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_agent_dispatch(
        agent: str,
        skill: str,
        confirm: bool,
        project: str = SESSION_FILE,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_agent_dispatch",
            {
                "project": project,
                "agent": agent,
                "skill": skill,
                "confirm": confirm,
                "arguments": arguments or {},
            },
        )

    @mcp.tool(
        name="ggen_create_selfplay",
        title="Run self-play",
        description=(
            "Run bounded authority, protocol, integrity, and convergence scenarios."
        ),
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_selfplay(
        confirm: bool,
        project: str = SESSION_FILE,
        output_root: str = ".ggen-create/selfplay",
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_selfplay",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
            },
        )

    @mcp.tool(
        name="ggen_create_parity_verify",
        title="Run parity verification",
        description=(
            "Execute reconstruction, variation, and optional original-reference parity."
        ),
        annotations=_WRITE,
        task=_TASK_OPTIONAL,
    )
    async def ggen_create_parity_verify(
        confirm: bool,
        variation_value: str,
        project: str = SESSION_FILE,
        output_root: str = ".ggen-create/parity",
        ggen_bin: str = "ggen",
        sync_args: list[str] | None = None,
        reference_dir: str | None = None,
        reference_id: str | None = None,
        force: bool = True,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_parity_verify",
            {
                "project": project,
                "confirm": confirm,
                "output_root": output_root,
                "variation_value": variation_value,
                "ggen_bin": ggen_bin,
                "sync_args": sync_args,
                "reference_dir": reference_dir,
                "reference_id": reference_id,
                "force": force,
            },
        )

    @mcp.tool(
        name="ggen_create_receipt_verify",
        title="Verify receipt",
        description="Recompute the latest or named native receipt digest.",
        annotations=_READ_ONLY,
    )
    def ggen_create_receipt_verify(
        project: str = SESSION_FILE,
        path: str | None = None,
    ) -> ToolResult | dict[str, Any]:
        return service.execute_named(
            "ggen_create_receipt_verify",
            {"project": project, "path": path},
        )

    @mcp.tool(
        name="ggen_create_receipt_chain_verify",
        title="Verify receipt chain",
        description=(
            "Verify native receipt roots, parents, branches, orphans, and latest pointer."
        ),
        annotations=_READ_ONLY,
    )
    def ggen_create_receipt_chain_verify(
        project: str = SESSION_FILE,
    ) -> dict[str, Any]:
        return _unwrap(
            service.execute_named(
                "ggen_create_receipt_chain_verify",
                {"project": project},
            )
        )

    @mcp.tool(
        name="ggen_create_doctor",
        title="Inspect runtime standing",
        description="Calculate evidence-backed runtime, package, ledger, and task standing.",
        annotations=_READ_ONLY,
    )
    def ggen_create_doctor(project: str = SESSION_FILE) -> dict[str, Any]:
        return _unwrap(
            service.execute_named("ggen_create_doctor", {"project": project})
        )

    @mcp.resource(
        "ggen-create://session",
        name="capture-session",
        title="Active capture",
        mime_type="application/json",
    )
    def capture_session() -> str:
        return service.read_resource("ggen-create://session")

    @mcp.resource(
        "ggen-create://skills",
        name="skills",
        title="Canonical create-time skills",
        mime_type="application/json",
    )
    def skills_resource() -> str:
        return service.read_resource("ggen-create://skills")

    @mcp.resource(
        "ggen-create://agents",
        name="agents",
        title="Bounded agents",
        mime_type="application/json",
    )
    def agents_resource() -> str:
        return service.read_resource("ggen-create://agents")

    @mcp.resource(
        "ggen-create://receipts/latest",
        name="latest-receipt",
        title="Latest native receipt",
        mime_type="application/json",
    )
    def latest_receipt() -> str:
        return service.read_resource("ggen-create://receipts/latest")

    @mcp.resource(
        "ggen-create://receipts/chain",
        name="receipt-chain",
        title="Native receipt ledger verification",
        mime_type="application/json",
    )
    def receipt_chain() -> str:
        return service.read_resource("ggen-create://receipts/chain")

    @mcp.resource(
        "ggen-create://doctor",
        name="doctor",
        title="Evidence-backed runtime standing",
        mime_type="application/json",
    )
    def doctor_resource() -> str:
        return service.read_resource("ggen-create://doctor")

    @mcp.prompt(
        name="create-factory",
        title="Create an admitted factory",
        description="Inspect, plan, apply, verify, and receipt.",
    )
    def create_factory_prompt(goal: str) -> str:
        return service.render_prompt("create-factory", {"goal": goal})

    @mcp.prompt(
        name="repair-factory",
        title="Repair a drifting factory",
        description="Use bounded integrity-aware autonomic convergence.",
    )
    def repair_factory_prompt(symptom: str) -> str:
        return service.render_prompt("repair-factory", {"symptom": symptom})

    @mcp.prompt(
        name="certify-factory",
        title="Calculate standing",
        description="Verify package, receipts, tasks, and authority.",
    )
    def certify_factory_prompt() -> str:
        return service.render_prompt("certify-factory", {})

    return mcp


def stdio_main(root: Path | None = None) -> int:
    create_mcp_server(root or Path.cwd()).run()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ggen-create-mcp")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    raise SystemExit(stdio_main(Path(args.root)))


async def run_mcp_selfplay_checks(
    root: Path,
    *,
    output_root: Path,
) -> list[tuple[str, bool, dict[str, Any]]]:
    """Exercise FastMCP lifecycle and durable task behavior for self-play."""
    from fastmcp import Client
    from mcp.shared.exceptions import McpError
    from mcp.shared.memory import create_client_server_memory_streams
    from mcp import ClientSession
    import anyio

    mcp = create_mcp_server(root)
    checks: list[tuple[str, bool, dict[str, Any]]] = []

    async with create_client_server_memory_streams() as (
        client_streams,
        server_streams,
    ):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with mcp._lifespan_manager():
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: mcp._mcp_server.run(
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                async with ClientSession(client_read, client_write) as session:
                    lifecycle_refused = False
                    try:
                        await session.list_tools()
                    except McpError:
                        lifecycle_refused = True
                    checks.append(
                        (
                            "mcp-lifecycle-refusal",
                            lifecycle_refused,
                            {},
                        )
                    )

                    init = await session.initialize()
                    checks.append(
                        (
                            "mcp-version-negotiation",
                            init.protocolVersion == MCP_PROTOCOL_VERSION,
                            {"protocolVersion": init.protocolVersion},
                        )
                    )

    async with Client(mcp) as client:
        task = await client.call_tool(
            "ggen_create_apply",
            {
                "confirm": True,
                "output_root": str(output_root / "mcp"),
            },
            task={"ttl": 60_000, "pollInterval": 50},
        )
        result = await task.result()
        checks.append(
            (
                "mcp-durable-task",
                task.status == "completed"
                and RELATED_TASK_KEY in (result.meta or {}),
                {
                    "status": task.status,
                    "meta_keys": sorted((result.meta or {}).keys()),
                },
            )
        )

    return checks


def run_mcp_selfplay_checks_sync(
    root: Path,
    *,
    output_root: Path,
) -> list[tuple[str, bool, dict[str, Any]]]:
    return asyncio.run(run_mcp_selfplay_checks(root, output_root=output_root))


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "RELATED_TASK_KEY",
    "SERVER_NAME",
    "SERVER_VERSION",
    "create_mcp_server",
    "main",
    "run_mcp_selfplay_checks_sync",
    "stdio_main",
]
