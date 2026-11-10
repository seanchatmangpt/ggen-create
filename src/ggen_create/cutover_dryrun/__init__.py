"""Cutover dry-run: read-only readiness probes for the v26.11.9 tickets."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .engine import (BLOCKED, FAIL, PASS, UNVERIFIED, REPOS, Clause, Result, combine, evaluate,
                     flip, read_digest, reset_reads)
from .tickets import BY_ID, PROBES

__all__ = ["run", "selftest", "validate_report", "PROBES", "BY_ID"]

IDENTITY_REPOS = ["srve", "xaas", "ggen-legacy", "ggen-create", "ggen-ecosystem"]
SCHEMA = Path(__file__).resolve().parents[3] / "schemas" / "cutover-dryrun-report.schema.json"


def selftest(home: Path, ids: list[str]) -> list[dict[str, str]]:
    """Every deterministic clause must refuse its own mutation; else VACUOUS_DRYRUN."""
    vacuous = []
    for tid in ids:
        for c in BY_ID[tid].clauses:
            mutated = flip(c)
            if mutated is None:
                continue
            if evaluate(mutated, home).status == PASS:
                vacuous.append({"ticket": tid, "clause": c.desc, "kind": c.kind})
    return vacuous


def _identity(home: Path) -> dict[str, str]:
    out = {}
    for name in IDENTITY_REPOS:
        repo = home / REPOS.get(name, name)
        try:
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=30, check=False).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            head = ""
        out[name] = head or "NO_GIT"
    return out


def validate_report(report: dict[str, Any]) -> str:
    """VALID | INVALID: <reason> | UNVERIFIED(schema-validator-absent)."""
    try:
        import jsonschema
    except ImportError:
        return "UNVERIFIED(schema-validator-absent)"
    if not SCHEMA.is_file():
        return "UNVERIFIED(schema-file-absent)"
    try:
        jsonschema.validate(report, json.loads(SCHEMA.read_text()))
    except jsonschema.ValidationError as exc:
        return f"INVALID: {exc.message}"
    return "VALID"


def run(home: Path | None = None, tickets: list[str] | None = None,
        do_selftest: bool = False) -> dict[str, Any]:
    home = home or Path.home()
    ids = tickets or [p.id for p in PROBES]
    unknown = [t for t in ids if t not in BY_ID]
    if unknown:
        raise ValueError(f"unknown tickets: {unknown}")
    reset_reads()
    rows = []
    for tid in ids:
        probe = BY_ID[tid]
        results: list[tuple[Clause, Result]] = [(c, evaluate(c, home)) for c in probe.clauses]
        rows.append({
            "ticket": tid,
            "title": probe.title,
            "tier": probe.tier,
            "standing": combine([r for _, r in results]),
            "clauses": [{"desc": c.desc, "kind": c.kind, "tier": c.tier,
                         "status": r.status, "detail": r.detail} for c, r in results],
        })
    _, per_first = read_digest()
    vacuous = selftest(home, ids) if do_selftest else None
    _, per_second = read_digest()
    changed = sorted(k for k in per_first if per_first[k] != per_second.get(k))
    counts = {s: sum(1 for r in rows if r["standing"] == s)
              for s in (PASS, FAIL, BLOCKED, UNVERIFIED)}
    if vacuous:
        verdict = "VACUOUS_DRYRUN"
    elif changed:
        verdict = "BLOCKED:UNSTABLE_EVIDENCE"
    elif counts[FAIL] or counts[BLOCKED]:
        verdict = "NOT_READY"
    elif counts[UNVERIFIED]:
        verdict = "READY_TO_REHEARSE_PENDING_T1_T2"
    else:
        verdict = "READY_TO_REHEARSE"
    report: dict[str, Any] = {
        "schema": "ggen-create.cutover.dryrun.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": counts,
        "identity": _identity(home),
        "readonly_proof": {"method": "read-set-digest", "files": len(per_first),
                           "changed_during_run": changed},
        "selftest": None if vacuous is None else {"vacuous": vacuous},
        "tickets": rows,
    }
    report["schema_validation"] = validate_report(report)
    return report
