from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
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
    digest_json,
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


def run_selfplay(
    session_path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    from .a2a import A2AService
    from .mcp import run_mcp_selfplay_checks_sync

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

    for name, passed, details in run_mcp_selfplay_checks_sync(
        root,
        output_root=output_root,
    ):
        scenarios.append(_check(name, passed, **details))

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

    # Phase 5 held-out replay evidence: receiver -> correspondence-analyst ->
    # admission-referee run against ggen-create's own repository - a real, external
    # subject the topology was not tuned against, not a fixture. Uses its own
    # AgentRuntime bound to the repo root (require_under needs subject_root to contain
    # what's being observed), separate from `agents`/`broker` above.
    repo_root = Path(__file__).resolve().parents[2]
    topology_agents = AgentRuntime(repo_root)

    def _run_topology_chain() -> dict[str, Any]:
        observation = topology_agents.dispatch(
            "receiver", "topology.observe", {"subject_root": "."},
            confirm=True,
        )
        graph = topology_agents.dispatch(
            "correspondence-analyst",
            "correspondence.analyze",
            {"subject_root": ".", "observation": observation["execution"]["result"]},
            confirm=True,
        )
        decision = topology_agents.dispatch(
            "admission-referee",
            "admission.decide",
            {
                "observation": observation["execution"]["result"],
                "graph": graph["execution"]["result"],
            },
            confirm=True,
        )
        return decision["execution"]["result"]

    first_decision = _run_topology_chain()
    second_decision = _run_topology_chain()
    scenarios.append(
        _check(
            "topology-chain-replay-deterministic",
            digest_json(first_decision) == digest_json(second_decision),
        )
    )

    scenarios.append(
        _check(
            "topology-chain-partial-alive-on-real-blockers",
            first_decision["standing"] == "PARTIAL_ALIVE"
            and {"blocker:agents", "blocker:release_control", "blocker:ggen_config"}
            <= set(first_decision["reasons"]),
            standing=first_decision["standing"],
            reasons=first_decision["reasons"],
        )
    )

    tampered_observation = topology_agents.dispatch(
        "receiver", "topology.observe", {"subject_root": "."},
        confirm=True,
    )["execution"]["result"]
    tampered_observation = json.loads(json.dumps(tampered_observation))
    tampered_observation["manifest"]["files"][0]["sha256"] = "sha256:" + "0" * 64
    tampered_graph = topology_agents.dispatch(
        "correspondence-analyst",
        "correspondence.analyze",
        {"subject_root": ".", "observation": tampered_observation},
        confirm=True,
    )["execution"]["result"]
    tampered_decision = topology_agents.dispatch(
        "admission-referee",
        "admission.decide",
        {"observation": tampered_observation, "graph": tampered_graph},
        confirm=True,
    )["execution"]["result"]
    scenarios.append(
        _check(
            "topology-chain-refused-on-tampered-observation",
            not tampered_graph["equal"] and tampered_decision["standing"] == "REFUSED",
            standing=tampered_decision["standing"],
        )
    )

    correspondence_route = topology_agents.route("analyze correspondence")
    admission_route = topology_agents.route("admit candidate")
    scenarios.append(
        _check(
            "topology-router-reaches-new-agents",
            correspondence_route["agent"] == "correspondence-analyst"
            and correspondence_route["skill"] == "correspondence.analyze"
            and admission_route["agent"] == "admission-referee"
            and admission_route["skill"] == "admission.decide",
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
