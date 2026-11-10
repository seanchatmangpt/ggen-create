"""Read-only dry-run engine for the srve cutover tickets.

A ticket is a list of clauses. Each clause is a pure check over files on disk (tier T0)
or an explicit UNVERIFIED marker for work that needs a scratch process (T1) or a live
backend (T2). Nothing here writes to the repositories under test.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

PASS = "PASS_PREDICTED"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
UNVERIFIED = "UNVERIFIED"

SKIP_DIRS = {".git", "node_modules", "_build", "deps", ".venv", "dist", "target"}
MAX_FILE_BYTES = 4 * 1024 * 1024
REPOS = {
    "srve": "srve",
    "xaas": "xaas",
    "ggen-legacy": "ggen-legacy",
    "ggen-create": "ggen-create",
    "ggen-ecosystem": "ggen-ecosystem",
    "gymact": "gymact",
    "zoela": "zoela",
}


_READS: list[Path] = []


def note_read(path: Path) -> None:
    _READS.append(path)


def reset_reads() -> None:
    _READS.clear()


def read_digest() -> tuple[str, dict[str, str]]:
    """Stat digest (size, mtime_ns) of every file the clauses read; MISSING when absent.

    Stat-based on purpose: the proof only has to show no read file changed during the run,
    and hashing tens of thousands of files twice dominates runtime.
    """
    per: dict[str, str] = {}
    for path in sorted(set(_READS)):
        try:
            if path.is_file():
                st = path.stat()
                per[str(path)] = f"{st.st_size}:{st.st_mtime_ns}"
            else:
                per[str(path)] = "MISSING"
        except OSError:
            per[str(path)] = "UNREADABLE"
    blob = json.dumps(per, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest(), per


@dataclass(frozen=True)
class Clause:
    kind: str
    desc: str
    args: dict[str, Any] = field(default_factory=dict)
    tier: str = "T0"


@dataclass(frozen=True)
class Result:
    status: str
    detail: str


def resolve(home: Path, ref: str) -> Path:
    """`repo:relative/path` -> absolute path; `home:` roots at the home directory."""
    root, _, rel = ref.partition(":")
    base = home if root == "home" else home / REPOS.get(root, root)
    return base / rel


def _files(path: Path):
    note_read(path)
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        return
    for item in sorted(path.rglob("*")):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if item.is_file() and not item.is_symlink():
            try:
                if item.stat().st_size <= MAX_FILE_BYTES:
                    note_read(item)
                    yield item
            except OSError:
                continue


def _expand(home: Path, refs: list[str]) -> list[Path]:
    out: list[Path] = []
    for ref in refs:
        target = resolve(home, ref)
        if any(c in ref for c in "*?["):
            out.extend(sorted(target.parent.glob(target.name)))
        else:
            out.append(target)
    return out


def _lines(path: Path):
    try:
        return path.read_text(errors="ignore").splitlines()
    except OSError:
        return []


def _count(home: Path, refs: list[str], pattern: str, exclude: str | None,
           distinct: bool) -> tuple[int, list[str]]:
    rx = re.compile(pattern)
    ex = re.compile(exclude) if exclude else None
    missing = [str(p) for p in _expand(home, refs) if not p.exists()]
    seen: list[str] = []
    n = 0
    for root in _expand(home, refs):
        for file in _files(root):
            if ex and ex.search(str(file)):
                continue
            for line in _lines(file):
                for m in rx.finditer(line):
                    n += 1
                    seen.append(m.group(0))
    if distinct:
        n = len(set(seen))
    return n, missing


def _cmp(op: str, got: int, want: int) -> bool:
    return {"eq": got == want, "ge": got >= want, "le": got <= want}[op]


def evaluate(clause: Clause, home: Path) -> Result:
    a = clause.args
    k = clause.kind
    if k == "unverified":
        return Result(UNVERIFIED, f"{clause.tier}: {a['reason']}")
    if k in ("exists", "not_exists"):
        paths = [resolve(home, r) for r in a["paths"]]
        for p in paths:
            note_read(p)
        present = [p for p in paths if p.exists()]
        if k == "exists":
            miss = [str(p) for p in paths if not p.exists()]
            return Result(FAIL, f"missing: {miss}") if miss else Result(PASS, "present")
        return Result(FAIL, f"should not exist: {[str(p) for p in present]}") if present \
            else Result(PASS, "absent")
    if k in ("count", "distinct"):
        got, missing = _count(home, a["paths"], a["pattern"], a.get("exclude"), k == "distinct")
        if missing and got == 0:
            return Result(BLOCKED, f"input missing: {missing[0]}")
        ok = _cmp(a["op"], got, a["n"])
        return Result(PASS if ok else FAIL, f"got {got}, need {a['op']} {a['n']}")
    if k == "absent":
        got, missing = _count(home, a["paths"], a["pattern"], a.get("exclude"), False)
        if missing and got == 0:
            return Result(BLOCKED, f"input missing: {missing[0]}")
        return Result(PASS if got == 0 else FAIL, f"{got} matches")
    if k == "json_len":
        path = resolve(home, a["path"])
        note_read(path)
        if not path.is_file():
            return Result(BLOCKED, f"input missing: {path}")
        data: Any = json.loads(path.read_text())
        for key in a.get("key", []):
            data = data[key]
        if "where" in a:
            f, v = a["where"]
            data = [r for r in data if r.get(f) == v]
        got = len(data)
        ok = _cmp(a["op"], got, a["n"])
        return Result(PASS if ok else FAIL, f"got {got}, need {a['op']} {a['n']}")
    if k == "json_required":
        path = resolve(home, a["path"])
        note_read(path)
        if not path.is_file():
            return Result(BLOCKED, f"input missing: {path}")
        have = set(json.loads(path.read_text()).get("required", []))
        miss = [f for f in a["fields"] if f not in have]
        return Result(FAIL, f"required lacks {miss}") if miss else Result(PASS, "all required")
    if k == "cmd":
        return _run_cmd(a, home)
    if k == "fresh":
        return _fresh(a, home)
    if k == "skills":
        from ..skills import SKILLS

        have = {s.name: (s.authority, s.requires_confirmation) for s in SKILLS}
        miss = [n for n, spec in a["want"].items() if have.get(n) != tuple(spec)]
        return Result(FAIL, f"unregistered or wrong: {miss}") if miss else Result(PASS, "registered")
    raise ValueError(f"unknown clause kind {k}")


def _head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _fresh(a: dict[str, Any], home: Path) -> Result:
    """A manifest is fresh when its recorded source_shas equal each source repo's HEAD."""
    path = resolve(home, a["path"])
    note_read(path)
    if not path.is_file():
        return Result(BLOCKED, f"input missing: {path}")
    recorded = json.loads(path.read_text()).get("source_shas", {})
    stale = []
    for name in a["repos"]:
        head = _head(home / REPOS.get(str(name), str(name)))
        if not head:
            return Result(BLOCKED, f"no git HEAD for {name}")
        if recorded.get(name) != head:
            stale.append(f"{name}: manifest {str(recorded.get(name))[:8]} != HEAD {head[:8]}")
    return Result(FAIL, "stale: " + "; ".join(stale)) if stale else Result(PASS, "manifest matches HEAD")


_AST_PARSE = "import ast,sys;ast.parse(open(sys.argv[1]).read())"


def _argv(home: Path, raw: list[str]) -> list[str]:
    return [str(resolve(home, x[1:])) if x.startswith("@") else x for x in raw]


def _cmd_allowed(argv: list[str]) -> bool:
    """Read-only allowlist: syntax checks only. Repo scripts are never executed: a script that
    predates a flag would ignore it and run for real (witnessed: bin/golden-court seeded xaas)."""
    if len(argv) == 3 and argv[:2] == ["bash", "-n"]:
        return True
    if len(argv) == 4 and argv[:3] == ["python3", "-c", _AST_PARSE][:3] and argv[2] == _AST_PARSE:
        return True
    return False


def _run_cmd(a: dict[str, Any], home: Path) -> Result:
    argv = _argv(home, list(a["argv"]))
    if not _cmd_allowed(argv):
        return Result(FAIL, f"CMD_NOT_ALLOWLISTED: {argv[:3]}")
    target = Path(argv[-1])
    note_read(target)
    if not target.is_file():
        return Result(BLOCKED, f"input missing: {target}")
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=int(a.get("timeout", 30)),
                              cwd=str(home), check=False)
    except subprocess.TimeoutExpired:
        return Result(FAIL, "timeout")
    want = int(a["expect_rc"])
    return Result(PASS if proc.returncode == want else FAIL, f"rc {proc.returncode}, need {want}")


def flip(clause: Clause) -> Clause | None:
    """Return a mutation of the clause that a non-vacuous check must refuse."""
    a = dict(clause.args)
    k = clause.kind
    if k == "unverified":
        return None
    if k == "cmd":
        a["expect_rc"] = int(a["expect_rc"]) + 99
    elif k == "fresh":
        a["repos"] = ["__bogus_repo__"]
    elif k == "exists":
        a["paths"] = [p + ".dryrun-nonexistent" for p in a["paths"]]
    elif k == "not_exists":
        a["paths"] = ["srve:"]
    elif k in ("count", "distinct"):
        a["op"], a["n"] = ("eq", a["n"] + 1) if a["op"] == "eq" else \
            (("ge", a["n"] + 10**9) if a["op"] == "ge" else ("le", -1))
    elif k == "absent":
        a["pattern"] = "."
    elif k == "json_len":
        a["op"], a["n"] = ("eq", a["n"] + 1) if a["op"] == "eq" else \
            (("ge", a["n"] + 10**9) if a["op"] == "ge" else ("le", -1))
    elif k == "json_required":
        a["fields"] = list(a["fields"]) + ["__dryrun_bogus_field__"]
    elif k == "skills":
        a["want"] = {**a["want"], "cutover.__bogus__": ["SELECT", False]}
    return replace(clause, args=a)


def combine(results: list[Result]) -> str:
    order = [FAIL, BLOCKED, UNVERIFIED]
    for status in order:
        if any(r.status == status for r in results):
            return status
    return PASS
