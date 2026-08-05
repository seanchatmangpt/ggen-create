from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .model import GgenCreateError
from .skills import Broker, SkillRegistry


@dataclass(frozen=True)
class AgentSpec:
    name: str
    purpose: str
    skills: tuple[str, ...]
    authority: str = "CONSTRUCT_ONLY"
    may_actuate: bool = False
    handoff: tuple[str, ...] = ()

    @property
    def role(self) -> str:
        return self.purpose

    @property
    def produces(self) -> str:
        return "bounded create-time graph or receipted execution"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["skills"] = list(self.skills)
        value["handoff"] = list(self.handoff)
        return value


AGENTS = (
    AgentSpec("receiver", "Fence and inspect the subject.", ("capture.inspect",), handoff=("correspondence-analyst",)),
    AgentSpec("correspondence-analyst", "Analyze generalization candidates.", ("capture.inspect", "automatic.plan"), handoff=("admission-referee",)),
    AgentSpec("manufacturing-architect", "Plan and manufacture ggen packages.", ("automatic.plan", "package.build", "automatic.create", "autonomic.run"), handoff=("verification-architect",)),
    AgentSpec("verification-architect", "Design and execute parity obligations.", ("parity.verify",), handoff=("admission-referee",)),
    AgentSpec("skill-architect", "Inspect canonical skill contracts.", ("skills.list",), handoff=("topology-architect",)),
    AgentSpec("topology-architect", "Inspect and route bounded agents.", ("agents.list", "agents.route"), handoff=("admission-referee",)),
    AgentSpec("admission-referee", "Admit or refuse candidate transitions.", ("capture.inspect", "automatic.plan", "receipt.verify"), handoff=("adversarial-verifier",)),
    AgentSpec("adversarial-verifier", "Run bounded adversarial self-play.", ("selfplay.run", "receipt.verify"), handoff=("certifier",)),
    AgentSpec("certifier", "Verify receipts and calculate standing.", ("receipt.verify", "skills.list", "agents.list")),
)
_BY_NAME = {agent.name: agent for agent in AGENTS}


class AgentRuntime:
    def __init__(self, subject_root: Path):
        self.subject_root = subject_root.resolve()
        self.skills = SkillRegistry()
        self.broker = Broker(self.subject_root)

    def list(self) -> list[dict[str, Any]]:
        return [agent.to_dict() for agent in AGENTS]

    def get(self, name: str) -> AgentSpec:
        try:
            return _BY_NAME[name]
        except KeyError as exc:
            raise GgenCreateError("AGENT_NOT_FOUND_REFUSED", name) from exc

    def route(self, goal: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = goal.strip().lower()
        routes = (
            (("selfplay", "adversarial", "red team"), "adversarial-verifier", "selfplay.run"),
            (("verify", "parity", "test"), "verification-architect", "parity.verify"),
            (("autonomic", "converge", "heal"), "manufacturing-architect", "autonomic.run"),
            (("manufacture", "build", "package", "automatic"), "manufacturing-architect", "automatic.plan"),
            (("skill",), "skill-architect", "skills.list"),
            (("agent", "topology", "route"), "topology-architect", "agents.list"),
            (("receipt", "certify"), "certifier", "receipt.verify"),
            (("inspect", "capture", "receive"), "receiver", "capture.inspect"),
        )
        for words, agent, skill in routes:
            if any(word in text for word in words):
                return {"agent": agent, "skill": skill, "goal": goal, "context": context or {}, "state": "CANDIDATE"}
        raise GgenCreateError("AGENT_ROUTE_UNSUPPORTED", goal)

    def plan(self, agent_name: str, skill_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        agent = self.get(agent_name)
        if agent.may_actuate:
            raise GgenCreateError("AMBIENT_AGENT_ACTUATION_REFUSED", agent_name)
        if skill_name not in agent.skills:
            raise GgenCreateError("AGENT_SKILL_AUTHORITY_REFUSED", f"{agent_name} cannot use {skill_name}")
        intent = self.skills.plan(skill_name, arguments)
        return {"agent": agent.to_dict(), "intent": intent.to_dict(), "handoff": list(agent.handoff), "state": "CANDIDATE"}

    def dispatch(self, agent_name: str, skill_name: str, arguments: dict[str, Any], *, session_path: Path, confirm: bool = False) -> dict[str, Any]:
        planned = self.plan(agent_name, skill_name, arguments)
        intent = self.skills.plan(skill_name, arguments)
        result = self.broker.execute(intent, session_path=session_path, confirm=confirm)
        return {**planned, "execution": result, "state": "ALIVE"}
