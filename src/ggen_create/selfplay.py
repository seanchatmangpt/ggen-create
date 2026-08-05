from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .agents import AGENTS, AgentRuntime
from .automatic import run_automatic
from .autonomic import AutonomicPolicy, run_autonomic
from .model import GgenCreateError
from .runtime import ReceiptStore, atomic_write_json, utc_now
from .skills import SKILLS, Broker, SkillRegistry


def _expect_refusal(code: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except GgenCreateError as exc:
        if exc.code != code:
            raise
        return {"state": "ALIVE", "expected_refusal": code}
    raise GgenCreateError("SELFPLAY_EXPECTED_REFUSAL_MISSING", code)


def run_selfplay(session_path: Path, *, output_root: Path) -> dict[str, Any]:
    root = session_path.parent.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    registry = SkillRegistry()
    agents = AgentRuntime(root)
    broker = Broker(root)
    scenarios: list[dict[str, Any]] = []

    scenarios.append({"name": "skills-have-no-ambient-do", "state": "ALIVE" if all(not skill.may_actuate for skill in SKILLS) else "REFUSED"})
    scenarios.append({"name": "agents-have-no-ambient-do", "state": "ALIVE" if all(not agent.may_actuate for agent in AGENTS) else "REFUSED"})
    scenarios.append({"name": "unauthorized-agent-skill", **_expect_refusal("AGENT_SKILL_AUTHORITY_REFUSED", lambda: agents.plan("receiver", "package.build", {}))})
    intent = registry.plan("package.build", {"output_root": str(output_root / "package")})
    scenarios.append({"name": "unconfirmed-do", **_expect_refusal("ACTUATION_CONFIRMATION_REQUIRED_REFUSED", lambda: broker.execute(intent, session_path=session_path))})
    executed = broker.execute(intent, session_path=session_path, confirm=True)
    scenarios.append({"name": "confirmed-do-receipted", "state": "ALIVE" if executed["receipt"] else "REFUSED"})
    first = agents.route("manufacture package")
    second = agents.route("manufacture package")
    scenarios.append({"name": "route-determinism", "state": "ALIVE" if (first["agent"], first["skill"]) == (second["agent"], second["skill"]) else "REFUSED"})
    automatic = run_automatic(session_path, output_root=output_root / "automatic", apply=True, confirm=True)
    scenarios.append({"name": "automatic-create", "state": automatic["state"]})
    autonomic = run_autonomic(session_path, output_root=output_root / "autonomic", policy=AutonomicPolicy(max_cycles=3, stable_cycles=1, apply=True, confirm=True))
    scenarios.append({"name": "autonomic-convergence", "state": "ALIVE" if autonomic["converged"] else "REFUSED"})

    failed = [item for item in scenarios if item["state"] != "ALIVE"]
    report = {
        "schema": "ggen-create-selfplay-report/0.1",
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
        outputs={"report": str(path), "failed_count": len(failed)},
    )
    report["report_path"] = str(path)
    report["receipt"] = receipt
    return report
