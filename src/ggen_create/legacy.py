from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Iterable

from .model import GgenCreateError
from .runtime import atomic_write_json, digest_file, digest_json, require_under

MANIFEST_SCHEMA = "ggen-create-legacy-manifest/1"
CONTRACT_SCHEMA = "ggen-create-to-ggen-legacy-contract/1"
RECEIPT_SCHEMA = "ggen-create-legacy-receipt/1"
DEFAULT_MAX_FILES = 50_000
DEFAULT_MAX_BYTES = 512 * 1024 * 1024

_EXCLUDED_DIRS = {
    ".git",
    ".ggen-create",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
}
_SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".ex", ".exs", ".go", ".h", ".hpp",
    ".java", ".js", ".jsx", ".kt", ".kts", ".php", ".py", ".rb",
    ".rs", ".scala", ".sh", ".swift", ".ts", ".tsx",
}
_DOC_SUFFIXES = {".adoc", ".md", ".mdx", ".rst", ".txt"}
_CONFIG_SUFFIXES = {".ini", ".json", ".toml", ".xml", ".yaml", ".yml"}
_ONTOLOGY_SUFFIXES = {".n3", ".nt", ".owl", ".rdf", ".trig", ".ttl"}
_TEMPLATE_SUFFIXES = {".hbs", ".j2", ".jinja", ".liquid", ".tera", ".tmpl"}

_WORKSTREAMS = (
    ("A", "observe", "Bind the exact predecessor tree and classify its evidence surfaces."),
    ("B", "align", "Separate observed facts, admitted authority, inferred intent, and exclusions."),
    ("C", "contract", "Manufacture a machine-readable receiving contract for ggen-legacy."),
    ("D", "model", "Project repository evidence into an ontology and deterministic manifest."),
    ("E", "template", "Admit one template owner for each manufactured path."),
    ("F", "manufacture", "Execute ggen against the admitted package."),
    ("G", "verify", "Run independent behavioral and structural verifiers."),
    ("H", "replay", "Recreate the same consequence from the same admitted subject."),
    ("I", "release", "Admit a bounded replacement release."),
    ("J", "sunset", "Retire the predecessor only after falsifiers remain closed."),
    ("K", "portfolio", "Aggregate standing without promoting unknowns."),
)


@dataclass(frozen=True)
class LegacyBuildResult:
    bundle_dir: Path
    changed: bool
    receipt_path: Path
    subject_digest: str
    bundle_digest: str


def _slug(value: str) -> str:
    result = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in result:
        result = result.replace("--", "-")
    if not result:
        raise GgenCreateError("PROGRAM_ID_REFUSED", repr(value))
    return result


def _git_dir(root: Path) -> Path | None:
    marker = root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        raw = marker.read_text(encoding="utf-8", errors="replace").strip()
        if raw.startswith("gitdir:"):
            target = Path(raw.split(":", 1)[1].strip())
            if not target.is_absolute():
                target = marker.parent / target
            return target.resolve()
    return None


def _git_identity(root: Path) -> dict[str, Any]:
    git_dir = _git_dir(root)
    if git_dir is None:
        return {"kind": "filesystem", "head": None, "ref": None}
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return {"kind": "git", "head": None, "ref": None}
    if not head.startswith("ref:"):
        return {"kind": "git", "head": head or None, "ref": None}
    ref = head.split(":", 1)[1].strip()
    commit = None
    try:
        commit = (git_dir / ref).read_text(encoding="utf-8").strip()
    except OSError:
        packed = git_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
                if line and not line.startswith(("#", "^")):
                    sha, _, name = line.partition(" ")
                    if name == ref:
                        commit = sha
                        break
    return {"kind": "git", "head": commit or None, "ref": ref}


def _classification(path: Path) -> str:
    parts = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in {"agents.md", "release_control.md", "security.md"} or parts[:1] in {
        ("authority",), ("governance",), ("product",), ("architecture",)
    }:
        return "authority"
    if "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if "schemas" in parts or name.endswith(".schema.json"):
        return "schema"
    if "templates" in parts or suffix in _TEMPLATE_SUFFIXES:
        return "template"
    if "ontology" in parts or suffix in _ONTOLOGY_SUFFIXES:
        return "ontology"
    if parts[:2] == (".github", "workflows") or name in {"dockerfile", "makefile", "justfile"}:
        return "workflow"
    if suffix in _SOURCE_SUFFIXES:
        return "source"
    if suffix in _DOC_SUFFIXES:
        return "documentation"
    if suffix in _CONFIG_SUFFIXES:
        return "configuration"
    return "other"


def _is_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\0" in handle.read(8192)


def _iter_files(root: Path, output_root: Path | None) -> Iterable[Path]:
    output_resolved = output_root.resolve() if output_root is not None else None
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(dirs):
            candidate = current_path / name
            if name in _EXCLUDED_DIRS:
                continue
            if candidate.is_symlink():
                raise GgenCreateError("SYMLINK_DIRECTORY_REFUSED", str(candidate))
            if output_resolved is not None:
                resolved = candidate.resolve()
                if resolved == output_resolved or resolved.is_relative_to(output_resolved):
                    continue
            kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                raise GgenCreateError("SYMLINK_FILE_REFUSED", str(path))
            if output_resolved is not None and path.resolve().is_relative_to(output_resolved):
                continue
            yield path


def plan_legacy_factory(
    subject_root: Path,
    *,
    output_root: Path | None = None,
    program_id: str = "ggen-legacy-foundry",
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    root = subject_root.resolve()
    if not root.is_dir():
        raise GgenCreateError("LEGACY_SUBJECT_NOT_FOUND_REFUSED", str(root))
    if max_files < 1 or max_bytes < 1:
        raise GgenCreateError(
            "OBSERVATION_BOUND_REFUSED",
            f"max_files={max_files} max_bytes={max_bytes}",
        )
    bounded_output = None
    if output_root is not None:
        bounded_output = require_under(root, output_root)
        if bounded_output == root:
            raise GgenCreateError("OUTPUT_ROOT_REFUSED", "output root cannot equal subject root")

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    counts: Counter[str] = Counter()
    for path in _iter_files(root, bounded_output):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        if len(entries) + 1 > max_files:
            raise GgenCreateError("FILE_COUNT_BOUND_REFUSED", f"more than {max_files} files")
        if total_bytes > max_bytes:
            raise GgenCreateError("BYTE_COUNT_BOUND_REFUSED", f"more than {max_bytes} bytes")
        kind = _classification(Path(relative))
        counts[kind] += 1
        mode = stat.S_IMODE(path.stat().st_mode)
        entries.append({
            "path": relative,
            "sha256": digest_file(path),
            "size": size,
            "mode": f"{mode:04o}",
            "class": kind,
            "binary": _is_binary(path),
        })
    entries.sort(key=lambda item: item["path"])
    identity = _git_identity(root)
    program = _slug(program_id)
    subject_digest = digest_json({
        "program_id": program,
        "identity": identity,
        "files": entries,
    })
    authority = {
        "agents": any(item["path"] == "AGENTS.md" for item in entries),
        "release_control": any(item["path"] == "RELEASE_CONTROL.md" for item in entries),
        "ggen_config": any(item["path"] == "ggen.toml" for item in entries),
        "ontology": counts["ontology"] > 0,
        "schemas": counts["schema"] > 0,
        "tests": counts["test"] > 0,
    }
    return {
        "schema": MANIFEST_SCHEMA,
        "program_id": program,
        "subject": {
            "root_name": root.name,
            "identity": identity,
            "digest": subject_digest,
            "file_count": len(entries),
            "byte_count": total_bytes,
        },
        "classification_counts": dict(sorted(counts.items())),
        "authority": authority,
        "blockers": [name for name, admitted in authority.items() if not admitted],
        "files": entries,
        "workstreams": [
            {
                "id": identifier,
                "name": name,
                "description": description,
                "input_state": "ALIVE" if identifier in {"A", "C", "D"} else "UNKNOWN",
            }
            for identifier, name, description in _WORKSTREAMS
        ],
        "exclusions": [
            "No source behavior is inferred from filenames alone.",
            "No generated bundle certifies ggen, ggen-legacy, production, compliance, release, or sunset.",
            "No shell, network, package-manager, deployment, or Git mutation authority is granted.",
            "Symlinks and paths outside the admitted subject are refused.",
        ],
        "standing": "PARTIAL_ALIVE" if entries else "UNKNOWN",
    }


def _ttl_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_ontology(manifest: dict[str, Any]) -> str:
    base = "https://chatmangpt.com/ggen-create/legacy#"
    lines = [
        "@prefix gc: <https://chatmangpt.com/ggen-create/legacy#> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "",
        f"<{base}{manifest['program_id']}> a gc:LegacyManufacturingProgram ;",
        f"  dcterms:identifier {_ttl_string(manifest['program_id'])} ;",
        f"  gc:subjectDigest {_ttl_string(manifest['subject']['digest'])} ;",
        f"  gc:fileCount {manifest['subject']['file_count']} ;",
        f"  gc:byteCount {manifest['subject']['byte_count']} ;",
        f"  gc:standing {_ttl_string(manifest['standing'])} .",
        "",
    ]
    for index, item in enumerate(manifest["files"], start=1):
        node = f"{base}file-{index:06d}"
        lines.extend([
            f"<{node}> a gc:ObservedArtifact ;",
            f"  gc:relativePath {_ttl_string(item['path'])} ;",
            f"  gc:sha256 {_ttl_string(item['sha256'])} ;",
            f"  gc:artifactClass {_ttl_string(item['class'])} ;",
            f"  gc:sizeBytes {item['size']} ;",
            f"  prov:wasDerivedFrom <{base}{manifest['program_id']}> .",
            "",
        ])
    return "\n".join(lines)


def receiving_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "producer": "ggen-create",
        "receiver": "ggen-legacy",
        "program_id": manifest["program_id"],
        "subject_digest": manifest["subject"]["digest"],
        "inputs": {
            "manifest": "manifest.json",
            "ontology": "ontology.ttl",
            "source_identity": manifest["subject"]["identity"],
        },
        "provided_workstreams": {
            "A": "ALIVE",
            "B": "PARTIAL_ALIVE",
            "C": "ALIVE",
            "D": "ALIVE",
        },
        "receiver_owned_workstreams": ["E", "F", "G", "H", "I", "J", "K"],
        "required_receiver_checks": [
            "verify exact manifest and receipt digests",
            "verify subject replay against the admitted source identity",
            "admit one template owner per manufactured path",
            "execute ggen sync twice and require byte-identical consequence or typed refusal",
            "execute independent behavioral acceptance",
            "preserve release and sunset as UNKNOWN until separately admitted",
        ],
        "refusals": [
            "SOURCE_IDENTITY_MISMATCH",
            "MANIFEST_DRIFT",
            "ONTOLOGY_DRIFT",
            "UNRECEIPTED_OUTPUT",
            "SELF_CERTIFICATION",
            "REPLAY_DIVERGENCE",
        ],
        "standing": "PARTIAL_ALIVE",
    }


def _readme(manifest: dict[str, Any]) -> str:
    return f"""# {manifest['program_id']} legacy receiving bundle

This directory is a deterministic `ggen-create` projection for `ggen-legacy`.

- subject digest: `{manifest['subject']['digest']}`
- observed files: `{manifest['subject']['file_count']}`
- observed bytes: `{manifest['subject']['byte_count']}`
- standing: `{manifest['standing']}`

`A`, `C`, and `D` are manufactured inputs. `ggen-legacy` still owns template admission,
real ggen execution, independent behavioral verification, replay, release, sunset, and
portfolio standing. This bundle never self-certifies those consequences.
"""


def _verify_script() -> str:
    return r'''#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def dj(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()
def df(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return "sha256:"+h.hexdigest()
def main():
    p=argparse.ArgumentParser(); p.add_argument("bundle", nargs="?", default="."); p.add_argument("--subject")
    a=p.parse_args(); root=Path(a.bundle).resolve(); receipt=json.loads((root/"receipt.json").read_text())
    expected=receipt["outputs"]; actual={}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "receipt.json": actual[path.relative_to(root).as_posix()]=df(path)
    checks={"output_set": set(actual)==set(expected), "output_digests": actual==expected}
    payload={k:v for k,v in receipt.items() if k!="receipt_digest"}
    checks["receipt_digest"]=dj(payload)==receipt.get("receipt_digest")
    if a.subject:
        subject=Path(a.subject).resolve(); manifest=json.loads((root/"manifest.json").read_text())
        checks["subject_files"]=all((subject/item["path"]).is_file() and df(subject/item["path"])==item["sha256"] for item in manifest["files"])
    report={"checks":checks,"valid":all(checks.values()),"state":"ALIVE" if all(checks.values()) else "BUILD_BROKEN"}
    print(json.dumps(report,indent=2,sort_keys=True)); raise SystemExit(0 if report["valid"] else 1)
if __name__=="__main__": main()
'''


def _replay_script() -> str:
    return r'''#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def df(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return "sha256:"+h.hexdigest()
def main():
    p=argparse.ArgumentParser(); p.add_argument("bundle", nargs="?", default="."); p.add_argument("--subject", required=True)
    a=p.parse_args(); root=Path(a.bundle).resolve(); subject=Path(a.subject).resolve(); manifest=json.loads((root/"manifest.json").read_text())
    differences=[]
    for item in manifest["files"]:
        path=subject/item["path"]
        if not path.is_file(): differences.append({"path":item["path"],"reason":"missing"})
        elif df(path)!=item["sha256"]: differences.append({"path":item["path"],"reason":"digest"})
    report={"subject_digest":manifest["subject"]["digest"],"differences":differences,"replay_match":not differences,"state":"ALIVE" if not differences else "BUILD_BROKEN"}
    print(json.dumps(report,indent=2,sort_keys=True)); raise SystemExit(0 if not differences else 1)
if __name__=="__main__": main()
'''


def _bundle_file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    }


def verify_legacy_bundle(
    bundle_root: Path,
    *,
    subject_root: Path | None = None,
) -> dict[str, Any]:
    root = bundle_root.resolve()
    try:
        receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError("LEGACY_BUNDLE_PARSE_REFUSED", str(exc)) from exc
    actual = _bundle_file_digests(root)
    expected = receipt.get("outputs")
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    checks: dict[str, bool] = {
        "receipt_schema": receipt.get("schema") == RECEIPT_SCHEMA,
        "manifest_schema": manifest.get("schema") == MANIFEST_SCHEMA,
        "output_set": isinstance(expected, dict) and set(actual) == set(expected),
        "output_digests": isinstance(expected, dict) and actual == expected,
        "receipt_digest": digest_json(payload) == receipt.get("receipt_digest"),
        "subject_digest_binding": manifest.get("subject", {}).get("digest") == receipt.get("subject_digest"),
    }
    drift: list[dict[str, str]] = []
    if subject_root is not None:
        subject = subject_root.resolve()
        for item in manifest.get("files", []):
            path = subject / item["path"]
            if not path.is_file():
                drift.append({"path": item["path"], "reason": "missing"})
            elif digest_file(path) != item["sha256"]:
                drift.append({"path": item["path"], "reason": "digest"})
        checks["subject_replay"] = not drift
    valid = all(checks.values())
    return {
        "bundle": str(root),
        "valid": valid,
        "checks": checks,
        "drift": drift,
        "subject_digest": receipt.get("subject_digest"),
        "bundle_digest": receipt.get("bundle_digest"),
        "state": "ALIVE" if valid else "BUILD_BROKEN",
    }


def build_legacy_bundle(
    subject_root: Path,
    output_root: Path,
    *,
    program_id: str = "ggen-legacy-foundry",
    force: bool = False,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> LegacyBuildResult:
    subject = subject_root.resolve()
    output = require_under(subject, output_root)
    if output == subject:
        raise GgenCreateError("OUTPUT_ROOT_REFUSED", "output root cannot equal subject root")
    manifest = plan_legacy_factory(
        subject,
        output_root=output,
        program_id=program_id,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    contract = receiving_contract(manifest)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        atomic_write_json(staging / "manifest.json", manifest)
        atomic_write_json(staging / "receiving-contract.json", contract)
        (staging / "ontology.ttl").write_text(render_ontology(manifest), encoding="utf-8")
        (staging / "README.md").write_text(_readme(manifest), encoding="utf-8")
        (staging / "verify_bundle.py").write_text(_verify_script(), encoding="utf-8")
        (staging / "replay_bundle.py").write_text(_replay_script(), encoding="utf-8")
        os.chmod(staging / "verify_bundle.py", 0o755)
        os.chmod(staging / "replay_bundle.py", 0o755)
        (staging / "ggen.toml").write_text(
            "[project]\nname = \"" + manifest["program_id"] + "\"\n\n"
            "[ontology]\nsource = \"ontology.ttl\"\n\n"
            "[templates]\ndir = \"templates\"\naggregate_modules = true\n\n"
            "[law]\nreflexive = true\n",
            encoding="utf-8",
        )
        (staging / "templates").mkdir()
        (staging / "templates" / ".keep").write_text("", encoding="utf-8")
        outputs = _bundle_file_digests(staging)
        bundle_digest = digest_json(outputs)
        receipt_payload = {
            "schema": RECEIPT_SCHEMA,
            "operation": "legacy.power",
            "state": "PARTIAL_ALIVE",
            "program_id": manifest["program_id"],
            "subject_digest": manifest["subject"]["digest"],
            "bundle_digest": bundle_digest,
            "outputs": outputs,
            "claims": {
                "observation": "ALIVE",
                "receiving_contract": "ALIVE",
                "ontology_projection": "ALIVE",
                "ggen_execution": "UNKNOWN",
                "behavioral_equivalence": "UNKNOWN",
                "release": "UNKNOWN",
                "sunset": "UNKNOWN",
            },
        }
        receipt = {**receipt_payload, "receipt_digest": digest_json(receipt_payload)}
        atomic_write_json(staging / "receipt.json", receipt)
        if output.exists():
            current_receipt = output / "receipt.json"
            if current_receipt.is_file():
                try:
                    current = json.loads(current_receipt.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    current = {}
                if (
                    current.get("bundle_digest") == bundle_digest
                    and current.get("subject_digest") == manifest["subject"]["digest"]
                ):
                    return LegacyBuildResult(
                        output,
                        False,
                        current_receipt,
                        manifest["subject"]["digest"],
                        bundle_digest,
                    )
            if not force:
                raise GgenCreateError("LEGACY_OUTPUT_EXISTS_REFUSED", str(output))
            shutil.rmtree(output)
        os.replace(staging, output)
        staging = None
        verification = verify_legacy_bundle(output, subject_root=subject)
        if not verification["valid"]:
            raise GgenCreateError(
                "LEGACY_BUNDLE_INTEGRITY_REFUSED",
                json.dumps(verification, sort_keys=True),
            )
        return LegacyBuildResult(
            output,
            True,
            output / "receipt.json",
            manifest["subject"]["digest"],
            bundle_digest,
        )
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
