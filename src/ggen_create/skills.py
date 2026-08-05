from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .model import GgenCreateError, SESSION_FILE
from .runtime import Intent, ReceiptStore, require_under


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    authority: str
    input_class: str
    output_class: str
    requires_confirmation: bool = False
    requires_session: bool = True
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
        name="capture.inspect",
        description="Inspect admitted correspondences.",
        authority="SELECT",
        input_class="CaptureSession",
        output_class="InspectionReport",
        verifier="mechanical-correspondence-count",
    ),
    SkillSpec(
        name="automatic.plan",
        description="Plan exemplar-to-package manufacture.",
        authority="CONSTRUCT",
        input_class="CaptureSession",
        output_class="AutomaticPlan",
        verifier="plan-schema",
    ),
    SkillSpec(
        name="package.build",
        description="Manufacture a deterministic ggen package.",
        authority="DO_INTENT",
        input_class="CaptureSession",
        output_class="GgenPackage",
        requires_confirmation=True,
        verifier="package-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="package.verify",
        description="Verify package contents against its package receipt.",
        authority="SELECT",
        input_class="GgenPackage",
        output_class="PackageIntegrityReport",
        verifier="sha256-package-manifest",
    ),
    SkillSpec(
        name="automatic.create",
        description="Execute automatic package manufacture.",
        authority="DO_INTENT",
        input_class="CaptureSession",
        output_class="AutomaticReport",
        requires_confirmation=True,
        verifier="automatic-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="automatic.watch",
        description="Observe bounded changes and manufacture only on drift.",
        authority="DO_INTENT",
        input_class="AutomaticWatchPolicy",
        output_class="AutomaticWatchReport",
        requires_confirmation=True,
        verifier="persisted-fingerprint-and-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="autonomic.cycle",
        description="Execute one bounded MAPE-K control cycle.",
        authority="DO_INTENT",
        input_class="AutonomicPolicy",
        output_class="AutonomicCycle",
        requires_confirmation=True,
        verifier="cycle-knowledge",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="autonomic.run",
        description="Run bounded MAPE-K convergence.",
        authority="DO_INTENT",
        input_class="AutonomicPolicy",
        output_class="AutonomicReport",
        requires_confirmation=True,
        verifier="convergence-and-receipt",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="parity.verify",
        description="Execute P0-P7 parity verification.",
        authority="DO_INTENT",
        input_class="ParityRequest",
        output_class="ParityReport",
        requires_confirmation=True,
        verifier="P0-P7-checkpoints",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="selfplay.run",
        description="Run adversarial native scenarios.",
        authority="DO_INTENT",
        input_class="SelfPlayRequest",
        output_class="SelfPlayReport",
        requires_confirmation=True,
        verifier="all-scenarios-alive",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="legacy.plan",
        description="Construct a bounded legacy-estate intake graph without actuation.",
        authority="CONSTRUCT",
        input_class="LegacyRepository",
        output_class="LegacyManufacturingPlan",
        requires_session=False,
        verifier="deterministic-subject-manifest",
    ),
    SkillSpec(
        name="legacy.power",
        description="Manufacture a deterministic ggen-legacy receiving bundle.",
        authority="DO_INTENT",
        input_class="LegacyRepository",
        output_class="LegacyReceivingBundle",
        requires_confirmation=True,
        requires_session=False,
        verifier="bundle-receipt-and-replay",
        refusals=_CONFIRMATION_REFUSAL,
    ),
    SkillSpec(
        name="legacy.verify",
        description="Independently verify a ggen-legacy receiving bundle and optional subject replay.",
        authority="SELECT",
        input_class="LegacyReceivingBundle",
        output_class="LegacyBundleVerification",
        requires_session=False,
        verifier="receipt-output-and-subject-digests",
    ),
    SkillSpec(
        name="receipt.verify",
        description="Verify a native receipt digest.",
        authority="SELECT",
        input_class="Receipt",
        output_class="ReceiptVerification",
        requires_session=False,
        verifier="sha256-recompute",
    ),
    SkillSpec(
        name="receipt.chain.verify",
        description="Verify the complete native receipt chain.",
        authority="SELECT",
        input_class="ReceiptLedger",
        output_class="ReceiptChainVerification",
        requires_session=False,
        verifier="parent-digest-chain",
    ),
    SkillSpec(
        name="doctor.inspect",
        description="Calculate evidence-backed runtime standing.",
        authority="SELECT",
        input_class="SubjectRoot",
        output_class="DoctorReport",
        requires_session=False,
        verifier="runtime-package-ledger-task-standing",
    ),
    SkillSpec(
        name="skills.list",
        description="List canonical skill contracts.",
        authority="SELECT",
        input_class="None",
        output_class="SkillGraph",
        requires_session=False,
        verifier="registry-closure",
    ),
    SkillSpec(
        name="agents.list",
        description="List bounded agent contracts.",
        authority="SELECT",
        input_class="None",
        output_class="AgentGraph",
        requires_session=False,
        verifier="topology-closure",
    ),
    SkillSpec(
        name="agents.route",
        description="Route a goal deterministically.",
        authority="SELECT",
        input_class="Goal",
        output_class="Handoff",
        requires_session=False,
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

    def _session(
        self,
        skill: SkillSpec,
        session_path: Path | None,
    ) -> Path:
        if session_path is None:
            if skill.requires_session:
                raise GgenCreateError(
                    "SESSION_REQUIRED_REFUSED",
                    f"{skill.name} requires a capture session",
                )
            return self.subject_root
        return require_under(self.subject_root, session_path)

    def execute(
        self,
        intent: Intent,
        *,
        session_path: Path | None = None,
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
        resolved_session = self._session(skill, session_path)

        try:
            result = self._dispatch(
                skill.name,
                resolved_session,
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
                        "session": str(resolved_session),
                    },
                    outputs={
                        "refusal": exc.code,
                        "detail": exc.detail,
                    },
                )
                exc.add_note(f"failure receipt: {receipt['path']}")
            raise
        except Exception as exc:
            receipt = None
            if skill.requires_confirmation:
                receipt = self.receipts.append(
                    operation=skill.name,
                    state="BLOCKED",
                    inputs={
                        "intent": intent.to_dict(),
                        "session": str(resolved_session),
                    },
                    outputs={
                        "refusal": "SKILL_INTERNAL_ERROR",
                        "type": type(exc).__name__,
                        "detail": str(exc),
                    },
                )
            failure = GgenCreateError(
                "SKILL_INTERNAL_ERROR",
                f"{skill.name}: {type(exc).__name__}: {exc}",
            )
            if receipt is not None:
                failure.add_note(f"failure receipt: {receipt['path']}")
            raise failure from exc

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
                    "session": str(resolved_session),
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
        if name == "legacy.plan":
            from .legacy import plan_legacy_factory

            return plan_legacy_factory(
                self._path(args.get("subject_root", ".")),
                output_root=self._path(
                    args.get("output_root", "foundry/generated/ggen-create")
                ),
                program_id=str(
                    args.get("program_id", "ggen-legacy-foundry")
                ),
                max_files=int(args.get("max_files", 50_000)),
                max_bytes=int(
                    args.get("max_bytes", 512 * 1024 * 1024)
                ),
            )
        if name == "legacy.power":
            from .legacy import build_legacy_bundle

            value = build_legacy_bundle(
                self._path(args.get("subject_root", ".")),
                self._path(
                    args.get("output_root", "foundry/generated/ggen-create")
                ),
                program_id=str(
                    args.get("program_id", "ggen-legacy-foundry")
                ),
                force=bool(args.get("force", False)),
                max_files=int(args.get("max_files", 50_000)),
                max_bytes=int(
                    args.get("max_bytes", 512 * 1024 * 1024)
                ),
            )
            return {
                "bundle": str(value.bundle_dir),
                "changed": value.changed,
                "receipt": str(value.receipt_path),
                "subject_digest": value.subject_digest,
                "bundle_digest": value.bundle_digest,
                "state": "PARTIAL_ALIVE",
            }
        if name == "legacy.verify":
            from .legacy import verify_legacy_bundle

            raw_subject = args.get("subject_root")
            return verify_legacy_bundle(
                self._path(
                    args.get(
                        "bundle_root",
                        args.get(
                            "output_root",
                            "foundry/generated/ggen-create",
                        ),
                    )
                ),
                subject_root=(
                    self._path(raw_subject)
                    if raw_subject
                    else None
                ),
            )
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
            raw_package = args.get("package")
            package = raw_package if raw_package else output / generator
            return verify_package(self._path(package))
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
        if name == "doctor.inspect":
            from .doctor import doctor_report

            return doctor_report(
                self.subject_root,
                project=str(args.get("project", SESSION_FILE)),
            )
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
