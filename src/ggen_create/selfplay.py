from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import time
from typing import Any, Callable

from .agents import AGENTS, AgentRuntime
from .automatic import run_automatic, watch_automatic
from .autonomic import AutonomicPolicy, run_autonomic
from .integrity import verify_package
from .model import GgenCreateError
from .runtime import (
    ReceiptStore,
    TaskStore,
    atomic_write_json,
    utc_now,
)
from .skills import SKILLS, Broker, SkillRegistry


def _expect_refusal(
    code: str,
    action: Callable[[], Any],
) -> dict[str, Any]:
    try:
        action()
    except GgenCreateError as exc:
        if exc.code != code:
            raise
        return {"state": "ALIVE", "expected_refusal": code}
    raise GgenCreateError("SELFPLAY_EXPECTED_REFUSAL_MISSING", code)


def _check(
    name: str,
    condition: bool,
    **details: Any,
) -> dict[str, Any]:
    return {
        "name": name,
        "state": "ALIVE" if condition else "REFUSED",
        **details,
    }


def _poll_mcp(server: Any, task_id: str) -> dict[str, Any]:
    for index in range(100):
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1000 + index,
                "method": "tasks/get",
                "params": {"taskId": task_id},
            }
        )
        task = response["result"]
        if task["status"] != "working":
            return task
        time.sleep(0.01)
    raise GgenCreateError(
        "SELFPLAY_TASK_TIMEOUT_REFUSED",
        task_id,
    )


def run_selfplay(
    session_path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    from .a2a import A2AService
    from .mcp import MCP_PROTOCOL_VERSION, McpServer

    session_path = session_path.resolve()
    root = session_path.parent.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    registry = SkillRegistry()
    agents = AgentRuntime(root)
    broker = Broker(root)
    scenarios: list[dict[str, Any]] = []

    scenarios.append(
        _check(
            "skills-have-no-ambient-do",
            all(not skill.may_actuate for skill in SKILLS),
            skill_count=len(SKILLS),
        )
    )
    scenarios.append(
        _check(
            "agents-have-no-ambient-do",
            all(not agent.may_actuate for agent in AGENTS),
            agent_count=len(AGENTS),
        )
    )
    scenarios.append(
        {
            "name": "unauthorized-agent-skill",
            **_expect_refusal(
                "AGENT_SKILL_AUTHORITY_REFUSED",
                lambda: agents.plan("receiver", "package.build", {}),
            ),
        }
    )

    intent = registry.plan(
        "package.build",
        {"output_root": str(output_root / "package")},
    )
    scenarios.append(
        {
            "name": "unconfirmed-do",
            **_expect_refusal(
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
                lambda: broker.execute(
                    intent,
                    session_path=session_path,
                ),
            ),
        }
    )
    tampered_intent = replace(intent, digest="sha256:" + "0" * 64)
    scenarios.append(
        {
            "name": "tampered-intent",
            **_expect_refusal(
                "INTENT_DIGEST_REFUSED",
                lambda: broker.execute(
                    tampered_intent,
                    session_path=session_path,
                    confirm=True,
                ),
            ),
        }
    )

    executed = broker.execute(
        intent,
        session_path=session_path,
        confirm=True,
    )
    scenarios.append(
        _check(
            "confirmed-do-receipted",
            bool(executed["receipt"])
            and executed["state"] == "ALIVE",
        )
    )
    repeat = broker.execute(
        registry.plan(
            "package.build",
            {"output_root": str(output_root / "package")},
        ),
        session_path=session_path,
        confirm=True,
    )
    scenarios.append(
        _check(
            "identical-package-no-op",
            repeat["result"]["changed"] is False,
        )
    )

    outside = root.parent / "ggen-create-selfplay-outside"
    scenarios.append(
        {
            "name": "path-escape-refused",
            **_expect_refusal(
                "PATH_ESCAPE_REFUSED",
                lambda: broker.execute(
                    registry.plan(
                        "package.build",
                        {"output_root": str(outside)},
                    ),
                    session_path=session_path,
                    confirm=True,
                ),
            ),
        }
    )

    first = agents.route("manufacture package")
    second = agents.route("manufacture package")
    scenarios.append(
        _check(
            "route-determinism",
            (first["agent"], first["skill"])
            == (second["agent"], second["skill"]),
        )
    )

    automatic_root = output_root / "automatic"
    automatic = run_automatic(
        session_path,
        output_root=automatic_root,
        apply=True,
        confirm=True,
    )
    scenarios.append(
        _check(
            "automatic-create",
            automatic["state"] == "ALIVE"
            and automatic["executed"][0]["integrity"]["valid"],
        )
    )
    stable_watch = watch_automatic(
        session_path,
        output_root=automatic_root,
        cycles=1,
        confirm=True,
    )
    scenarios.append(
        _check(
            "automatic-watch-persisted-no-op",
            stable_watch["converged"]
            and stable_watch["cycles"][0]["state"] == "STABLE"
            and not stable_watch["cycles"][0]["executed"],
        )
    )

    automatic_package = Path(automatic["executed"][0]["package"])
    (automatic_package / "ggen.toml").write_text(
        "[project]\nname = \"tampered\"\n",
        encoding="utf-8",
    )
    scenarios.append(
        _check(
            "package-corruption-detected",
            not verify_package(automatic_package)["valid"],
        )
    )
    repaired = run_autonomic(
        session_path,
        output_root=automatic_root,
        policy=AutonomicPolicy(
            max_cycles=3,
            stable_cycles=1,
            apply=True,
            confirm=True,
        ),
    )
    scenarios.append(
        _check(
            "autonomic-corruption-recovery",
            repaired["converged"]
            and verify_package(automatic_package)["valid"],
        )
    )

    task_store = TaskStore(root, "selfplay")
    terminal = task_store.create(
        kind="transition",
        request={"test": True},
    )
    task_store.complete(terminal["taskId"], {"ok": True})
    scenarios.append(
        {
            "name": "terminal-task-cancel-refused",
            **_expect_refusal(
                "TASK_NOT_CANCELABLE_REFUSED",
                lambda: task_store.cancel(terminal["taskId"]),
            ),
        }
    )
    expiring = task_store.create(
        kind="ttl",
        request={"test": True},
        ttl=1000,
    )
    expiring_path = task_store._path(expiring["taskId"])
    expiring["createdAt"] = "2000-01-01T00:00:00Z"
    atomic_write_json(expiring_path, expiring)
    scenarios.append(
        {
            "name": "expired-task-refused",
            **_expect_refusal(
                "TASK_EXPIRED_REFUSED",
                lambda: task_store.get(expiring["taskId"]),
            ),
        }
    )

    unsupported = McpServer(root).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "1900-01-01",
                "capabilities": {},
                "clientInfo": {"name": "selfplay", "version": "1"},
            },
        }
    )
    scenarios.append(
        _check(
            "mcp-version-refusal",
            unsupported is not None
            and unsupported.get("error", {}).get("code") == -32602,
        )
    )
    mcp = McpServer(root)
    pre_ready = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
    )
    scenarios.append(
        _check(
            "mcp-lifecycle-refusal",
            pre_ready is not None
            and pre_ready.get("error", {}).get("message")
            == "MCP_LIFECYCLE_REFUSED",
        )
    )
    initialized = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tasks": {}},
                "clientInfo": {"name": "selfplay", "version": "1"},
            },
        }
    )
    mcp.handle(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
    )
    task_response = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "ggen_create_apply",
                "arguments": {
                    "confirm": True,
                    "output_root": str(output_root / "mcp"),
                },
                "task": {"ttl": 60_000, "pollInterval": 50},
            },
        }
    )
    task_id = task_response["result"]["task"]["taskId"]
    mcp_task = _poll_mcp(mcp, task_id)
    mcp_result = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tasks/result",
            "params": {"taskId": task_id},
        }
    )
    scenarios.append(
        _check(
            "mcp-durable-task",
            initialized is not None
            and initialized["result"]["protocolVersion"]
            == MCP_PROTOCOL_VERSION
            and mcp_task["status"] == "completed"
            and mcp_result is not None
            and (
                "io.modelcontextprotocol/related-task"
                in mcp_result["result"]["_meta"]
            ),
        )
    )

    a2a = A2AService(
        root,
        base_url="http://127.0.0.1:8765",
    )
    first_message = a2a.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "selfplay-a2a-1",
                    "role": "ROLE_USER",
                    "contextId": "selfplay-context",
                    "parts": [
                        {
                            "data": {
                                "operation": "automatic.create",
                                "arguments": {
                                    "output_root": str(
                                        output_root / "a2a"
                                    )
                                },
                            }
                        }
                    ],
                }
            },
        }
    )
    pending = first_message["result"]["task"]
    second_message = a2a.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "selfplay-a2a-2",
                    "taskId": pending["id"],
                    "role": "ROLE_USER",
                    "contextId": "selfplay-context",
                    "parts": [
                        {
                            "data": {
                                "confirm": True,
                                "arguments": {},
                            }
                        }
                    ],
                }
            },
        }
    )
    completed = second_message["result"]["task"]
    fetched = a2a.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "GetTask",
            "params": {
                "id": pending["id"],
                "historyLength": 2,
            },
        }
    )
    scenarios.append(
        _check(
            "a2a-input-required-continuation",
            pending["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
            and completed["status"]["state"] == "TASK_STATE_COMPLETED"
            and len(fetched["result"]["task"].get("history", [])) == 2,
        )
    )

    isolated_root = output_root / "tamper-subject"
    isolated_root.mkdir(parents=True, exist_ok=True)
    isolated_store = ReceiptStore(isolated_root)
    isolated_receipt = isolated_store.append(
        operation="tamper.test",
        state="ALIVE",
        inputs={},
        outputs={"value": 1},
    )
    tampered = json.loads(
        Path(isolated_receipt["path"]).read_text(encoding="utf-8")
    )
    tampered["outputs"]["value"] = 2
    atomic_write_json(Path(isolated_receipt["path"]), tampered)
    scenarios.append(
        _check(
            "tampered-receipt-detected",
            not ReceiptStore.verify(
                Path(isolated_receipt["path"])
            )["valid"],
        )
    )

    chain = ReceiptStore(root).verify_chain()
    scenarios.append(
        _check(
            "receipt-chain-valid",
            chain["valid"],
            receipt_count=chain["count"],
        )
    )

    failed = [item for item in scenarios if item["state"] != "ALIVE"]
    report = {
        "schema": "ggen-create-selfplay-report/0.2",
        "timestamp": utc_now(),
        "state": "ALIVE" if not failed else "REFUSED",
        "scenario_count": len(scenarios),
        "failed_count": len(failed),
        "scenarios": scenarios,
    }
    path = output_root / "selfplay-report.json"
    atomic_write_json(path, report)
    receipt = ReceiptStore(root).append(
        operation="selfplay.run",
        state=report["state"],
        inputs={"session": str(session_path)},
        outputs={
            "report": str(path),
            "failed_count": len(failed),
            "scenario_count": len(scenarios),
        },
    )
    report["report_path"] = str(path)
    report["receipt"] = receipt
    return report
