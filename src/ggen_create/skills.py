from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .model import GgenCreateError
from .runtime import Intent, ReceiptStore, require_under


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    authority: str
    input_class: str
    output_class: str
    requires_confirmation: bool = False
    may_actuate: bool = False
    verifier: str = ""
    refusals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["refusals"] = list(self.refusals)
        return value


_CONFIRMATION_REFUSAL = ("ACTUATION_CONFIRMATION_REQUIRED_REFUSED",)
SKILLS = (
    SkillSpec(
        "capture.inspect",
        "Inspect admitted correspondences.",
        "SELECT",
        "CaptureSession",
        "InspectionReport",
        verifier="mechanical-correspondence-count",
    ),
    SkillSpec(
        "automatic.plan",
        "Plan exemplar-to-package manufacture.",
        "CONSTRUCT",
        "CaptureSession",
        "AutomaticPlan",
        verifier="plan-schema",
    ),
    SkillSpec(
        "package.build",
        "Manufacture a deterministic ggen package.",
        "DO_INTENT",
        "CaptureSession",
        "GgenPackage",
        True,
        verifier="package-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "package.verify",
        "Verify package contents against its package receipt.",
        "SELECT",
        "GgenPackage",
        "PackageIntegrityReport",
        verifier="sha256-package-manifest",
    ),
    SkillSpec(
        "automatic.create",
        "Execute automatic package manufacture.",
        "DO_INTENT",
        "CaptureSession",
        "AutomaticReport",
        True,
        verifier="automatic-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "automatic.watch",
        "Observe bounded changes and manufacture only on drift.",
        "DO_INTENT",
        "AutomaticWatchPolicy",
        "AutomaticWatchReport",
        True,
        verifier="persisted-fingerprint-and-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "autonomic.cycle",
        "Execute one bounded MAPE-K control cycle.",
        "DO_INTENT",
        "AutonomicPolicy",
        "AutonomicCycle",
        True,
        verifier="cycle-knowledge",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "autonomic.run",
        "Run bounded MAPE-K convergence.",
        "DO_INTENT",
        "AutonomicPolicy",
        "AutonomicReport",
        True,
        verifier="convergence-and-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "parity.verify",
        "Execute P0-P7 parity verification.",
        "DO_INTENT",
        "ParityRequest",
        "ParityReport",
        True,
        verifier="P0-P7-checkpoints",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "selfplay.run",
        "Run adversarial native scenarios.",
        "DO_INTENT",
        "SelfPlayRequest",
        "SelfPlayReport",
        True,
        verifier="all-scenarios-alive",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        "receipt.verify",
        "Verify a native receipt digest.",
        "SELECT",
        "Receipt",
        "ReceiptVerification",
        verifier="sha256-recompute",
    ),
    SkillSpec(
        "receipt.chain.verify",
        "Verify the complete native receipt chain.",
        "SELECT",
        "ReceiptLedger",
        "ReceiptChainVerification",
        verifier="parent-digest-chain",
    ),
    SkillSpec(
        "skills.list",
        "List canonical skill contracts.",
        "SELECT",
        "None",
        "SkillGraph",
        verifier="registry-closure",
    ),
    SkillSpec(
        "agents.list",
        "List bounded agent contracts.",
        "SELECT",
        "None",
        "AgentGraph",
        verifier="topology-closure",
    ),
    SkillSpec(
        "agents.route",
        "Route a goal deterministically.",
        "SELECT",
        "Goal",
        "Handoff",
        verifier="deterministic-router",
    ),
)
_BY_NAME = {skill.name: skill for skill in SKILLS}


class SkillRegistry:
    def list(self) -> list[dict[str, Any]]:
        return [skill.to_dict() for skill in SKILLS]

    def get(self, name: str) -> SkillSpec:
        try:
            return _BY_NAME[name]
        except KeyError as exc:
            raise GgenCreateError("SKILL_NOT_FOUND_REFUSED", name) from exc

    def plan(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Intent:
        skill = self.get(name)
        return Intent.create(
            name,
            arguments or {},
            authority=skill.authority,
            requires_confirmation=skill.requires_confirmation,
        )


class Broker:
    """Exclusive DO boundary. Skills and agents submit verified intents only."""

    def __init__(self, subject_root: Path):
        self.subject_root = subject_root.resolve()
        self.registry = SkillRegistry()
        self.receipts = ReceiptStore(self.subject_root)

    def _path(self, value: str | Path) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.subject_root / candidate
        return require_under(self.subject_root, candidate)

    def execute(
        self,
        intent: Intent,
        *,
        session_path: Path,
        confirm: bool = False,
    ) -> dict[str, Any]:
        intent.verify()
        skill = self.registry.get(intent.action)
        if intent.authority != skill.authority:
            raise GgenCreateError(
                "INTENT_AUTHORITY_REFUSED",
                f"{intent.authority} != {skill.authority}",
            )
        if skill.may_actuate:
            raise GgenCreateError(
                "AMBIENT_SKILL_ACTUATION_REFUSED",
                skill.name,
            )
        if skill.authority == "DO_INTENT" and not skill.requires_confirmation:
            raise GgenCreateError(
                "UNCONFIRMED_DO_CONTRACT_REFUSED",
                skill.name,
            )
        if skill.requires_confirmation and not confirm:
            raise GgenCreateError(
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
                skill.name,
            )
        session_path = require_under(self.subject_root, session_path)

        try:
            result = self._dispatch(
                skill.name,
                session_path,
                dict(intent.arguments),
                confirm,
            )
        except GgenCreateError as exc:
            receipt = None
            if skill.requires_confirmation:
                receipt = self.receipts.append(
                    operation=skill.name,
                    state="BLOCKED",
                    inputs={
                        "intent": intent.to_dict(),
                        "session": str(session_path),
                    },
                    outputs={
                        "refusal": exc.code,
                        "detail": exc.detail,
                    },
                )
                exc.add_note(f"failure receipt: {receipt['path']}")
            raise

        standing = (
            str(result.get("state", "ALIVE"))
            if isinstance(result, dict)
            else "ALIVE"
        )
        receipt = None
        if skill.requires_confirmation:
            receipt = self.receipts.append(
                operation=skill.name,
                state=standing,
                inputs={
                    "intent": intent.to_dict(),
                    "session": str(session_path),
                },
                outputs={"result": result},
            )
        return {
            "skill": skill.to_dict(),
            "intent": intent.to_dict(),
            "result": result,
            "receipt": receipt,
            "state": standing,
        }

    def _policy(self, args: dict[str, Any], confirm: bool) -> Any:
        from .autonomic import AutonomicPolicy

        return AutonomicPolicy(
            max_cycles=int(args.get("max_cycles", 4)),
            stable_cycles=int(args.get("stable_cycles", 2)),
            interval_seconds=float(args.get("interval_seconds", 0)),
            apply=bool(args.get("apply", True)),
            confirm=confirm,
            verify=bool(args.get("verify")),
            variation_value=args.get("variation_value"),
            ggen_bin=str(args.get("ggen_bin", "ggen")),
        )

    def _dispatch(
        self,
        name: str,
        session: Path,
        args: dict[str, Any],
        confirm: bool,
    ) -> Any:
        output = self._path(args.get("output_root", "_ggen"))
        if name == "capture.inspect":
            from .inspect import inspect_session

            return inspect_session(session)
        if name == "automatic.plan":
            from .automatic import automatic_plan

            return automatic_plan(
                session,
                output_root=output,
                variation_value=args.get("variation_value"),
                verify=bool(args.get("verify")),
            )
        if name == "package.build":
            from .integrity import verify_package
            from .package import build_package

            value = build_package(
                session,
                output,
                force=bool(args.get("force")),
            )
            integrity = verify_package(value.package_dir)
            if not integrity["valid"]:
                raise GgenCreateError(
                    "PACKAGE_INTEGRITY_REFUSED",
                    str(integrity),
                )
            return {
                "package": str(value.package_dir),
                "changed": value.changed,
                "archived_previous": (
                    str(value.archived_previous)
                    if value.archived_previous
                    else None
                ),
                "receipt": str(value.receipt_path),
                "integrity": integrity,
                "state": "ALIVE",
            }
        if name == "package.verify":
            from .integrity import verify_package
            from .session import load_session

            generator = load_session(session)["name"]
            return verify_package(
                self._path(args.get("package", output / generator))
            )
        if name == "automatic.create":
            from .automatic import run_automatic

            return run_automatic(
                session,
                output_root=output,
                apply=True,
                confirm=confirm,
                verify=bool(args.get("verify")),
                ggen_bin=str(args.get("ggen_bin", "ggen")),
                variation_value=args.get("variation_value"),
                sync_args=args.get("sync_args"),
                force=bool(args.get("force")),
            )
        if name == "automatic.watch":
            from .automatic import watch_automatic

            return watch_automatic(
                session,
                output_root=output,
                cycles=int(args.get("cycles", 2)),
                interval_seconds=float(args.get("interval_seconds", 0)),
                confirm=confirm,
                verify=bool(args.get("verify")),
                ggen_bin=str(args.get("ggen_bin", "ggen")),
                variation_value=args.get("variation_value"),
                force=bool(args.get("force")),
            )
        if name == "autonomic.cycle":
            from .autonomic import autonomic_cycle

            return autonomic_cycle(
                session,
                output_root=output,
                policy=self._policy(args, confirm),
            )
        if name == "autonomic.run":
            from .autonomic import run_autonomic

            return run_autonomic(
                session,
                output_root=output,
                policy=self._policy(args, confirm),
            )
        if name == "parity.verify":
            from .verify import verify_parity

            variation = args.get("variation_value")
            if not isinstance(variation, str) or not variation:
                raise GgenCreateError(
                    "VARIATION_REQUIRED_REFUSED",
                    "variation_value is required",
                )
            reference_dir = (
                self._path(args["reference_dir"])
                if args.get("reference_dir")
                else None
            )
            return verify_parity(
                session,
                output_root=self._path(
                    args.get("output_root", ".ggen-create/parity")
                ),
                ggen_bin=str(args.get("ggen_bin", "ggen")),
                variation_value=variation,
                sync_args=args.get("sync_args"),
                reference_dir=reference_dir,
                reference_id=args.get("reference_id"),
                force=bool(args.get("force", True)),
            )
        if name == "selfplay.run":
            from .selfplay import run_selfplay

            return run_selfplay(
                session,
                output_root=self._path(
                    args.get("output_root", ".ggen-create/selfplay")
                ),
            )
        if name == "receipt.verify":
            raw = args.get("path")
            if not raw:
                latest = self.receipts.latest()
                if not latest:
                    raise GgenCreateError(
                        "RECEIPT_NOT_FOUND_REFUSED",
                        "no latest receipt",
                    )
                raw = latest["path"]
            return ReceiptStore.verify(self._path(raw))
        if name == "receipt.chain.verify":
            return self.receipts.verify_chain()
        if name == "skills.list":
            return self.registry.list()
        if name in {"agents.list", "agents.route"}:
            from .agents import AgentRuntime

            runtime = AgentRuntime(self.subject_root)
            if name == "agents.list":
                return runtime.list()
            return runtime.route(
                str(args.get("goal", "")),
                args.get("context", {}),
            )
        raise GgenCreateError("SKILL_NOT_IMPLEMENTED_REFUSED", name)
