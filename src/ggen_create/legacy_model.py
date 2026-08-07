from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterable

from .model import APP_VERSION, GgenCreateError
from .runtime import digest_file, digest_json, require_under

MANIFEST_SCHEMA = "ggen-create-legacy-manifest/1"
CONTRACT_SCHEMA = "ggen-create-to-ggen-legacy-contract/1"
RECEIPT_SCHEMA = "ggen-create-legacy-receipt/1"
DEFAULT_MAX_FILES = 50_000
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_PRODUCER_REPOSITORY = "seanchatmangpt/ggen-create"
UNKNOWN_PRODUCER_COMMIT = "UNKNOWN"

EXCLUDED_DIRS = {
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
            return (marker.parent / target).resolve() if not target.is_absolute() else target.resolve()
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


def _producer_identity(repository: str, commit: str) -> dict[str, str]:
    resolved_commit = commit
    if resolved_commit == UNKNOWN_PRODUCER_COMMIT:
        resolved_commit = os.environ.get("GGEN_CREATE_SOURCE_COMMIT", UNKNOWN_PRODUCER_COMMIT)
    if resolved_commit == UNKNOWN_PRODUCER_COMMIT:
        resolved_commit = _git_identity(Path(__file__).resolve().parents[2]).get("head") or UNKNOWN_PRODUCER_COMMIT
    if resolved_commit != UNKNOWN_PRODUCER_COMMIT and (
        len(resolved_commit) != 40
        or any(ch not in "0123456789abcdef" for ch in resolved_commit)
    ):
        raise GgenCreateError("PRODUCER_COMMIT_REFUSED", resolved_commit)
    return {
        "name": "ggen-create",
        "version": APP_VERSION,
        "repository": repository,
        "commit": resolved_commit,
    }


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


def iter_legacy_files(root: Path, output_root: Path | None) -> Iterable[Path]:
    output_resolved = output_root.resolve() if output_root is not None else None
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(dirs):
            candidate = current_path / name
            if name in EXCLUDED_DIRS:
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
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise GgenCreateError("LEGACY_FILE_STAT_REFUSED", f"{path}: {exc}") from exc
            if not stat.S_ISREG(mode):
                raise GgenCreateError("SPECIAL_FILE_REFUSED", str(path))
            yield path


def plan_legacy_factory(
    subject_root: Path,
    *,
    output_root: Path | None = None,
    program_id: str = "ggen-legacy-foundry",
    producer_repository: str = DEFAULT_PRODUCER_REPOSITORY,
    producer_commit: str = UNKNOWN_PRODUCER_COMMIT,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    root = subject_root.resolve()
    if not root.is_dir():
        raise GgenCreateError("LEGACY_SUBJECT_NOT_FOUND_REFUSED", str(root))
    if max_files < 1 or max_bytes < 1:
        raise GgenCreateError("OBSERVATION_BOUND_REFUSED", f"max_files={max_files} max_bytes={max_bytes}")
    bounded_output = None
    if output_root is not None:
        bounded_output = require_under(root, output_root)
        if bounded_output == root:
            raise GgenCreateError("OUTPUT_ROOT_REFUSED", "output root cannot equal subject root")

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    counts: Counter[str] = Counter()
    for path in iter_legacy_files(root, bounded_output):
        relative = path.relative_to(root).as_posix()
        try:
            metadata = path.stat()
            content_digest = digest_file(path)
            binary = _is_binary(path)
        except OSError as exc:
            raise GgenCreateError("LEGACY_FILE_READ_REFUSED", f"{path}: {exc}") from exc
        total_bytes += metadata.st_size
        if len(entries) + 1 > max_files:
            raise GgenCreateError("FILE_COUNT_BOUND_REFUSED", f"more than {max_files} files")
        if total_bytes > max_bytes:
            raise GgenCreateError("BYTE_COUNT_BOUND_REFUSED", f"more than {max_bytes} bytes")
        kind = _classification(Path(relative))
        counts[kind] += 1
        entries.append({
            "path": relative,
            "sha256": content_digest,
            "size": metadata.st_size,
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
            "class": kind,
            "binary": binary,
        })
    entries.sort(key=lambda item: item["path"])
    identity = _git_identity(root)
    program = _slug(program_id)
    subject_digest = digest_json({"program_id": program, "identity": identity, "files": entries})
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
        "producer_identity": _producer_identity(producer_repository, producer_commit),
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
            "Symlinks, special files, and paths outside the admitted subject are refused.",
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
        lines.extend([
            f"<{base}file-{index:06d}> a gc:ObservedArtifact ;",
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
        "producer_identity": manifest["producer_identity"],
        "receiver": "ggen-legacy",
        "program_id": manifest["program_id"],
        "subject_digest": manifest["subject"]["digest"],
        "inputs": {
            "manifest": "manifest.json",
            "ontology": "ontology.ttl",
            "source_identity": manifest["subject"]["identity"],
        },
        "provided_workstreams": {"A": "ALIVE", "B": "PARTIAL_ALIVE", "C": "ALIVE", "D": "ALIVE"},
        "receiver_owned_workstreams": ["E", "F", "G", "H", "I", "J", "K"],
        "required_receiver_checks": [
            "verify exact manifest, producer identity, receipt digests, and output modes",
            "verify exact subject replay against the admitted source identity and file set",
            "admit one template owner per manufactured path",
            "execute ggen sync twice and require byte-identical consequence or typed refusal",
            "execute independent behavioral acceptance",
            "preserve release and sunset as UNKNOWN until separately admitted",
        ],
        "refusals": [
            "SOURCE_IDENTITY_MISMATCH",
            "PRODUCER_IDENTITY_MISMATCH",
            "MANIFEST_DRIFT",
            "ONTOLOGY_DRIFT",
            "UNRECEIPTED_OUTPUT",
            "SELF_CERTIFICATION",
            "REPLAY_DIVERGENCE",
        ],
        "standing": "PARTIAL_ALIVE",
    }


def render_readme(manifest: dict[str, Any]) -> str:
    return f"""# {manifest['program_id']} legacy receiving bundle

This directory is a deterministic `ggen-create` projection for `ggen-legacy`.

- subject digest: `{manifest['subject']['digest']}`
- producer: `{manifest['producer_identity']['repository']}@{manifest['producer_identity']['commit']}`
- observed files: `{manifest['subject']['file_count']}`
- observed bytes: `{manifest['subject']['byte_count']}`
- standing: `{manifest['standing']}`

`A`, `C`, and `D` are manufactured inputs. `ggen-legacy` still owns template admission,
real ggen execution, independent behavioral verification, replay, release, sunset, and
portfolio standing. This bundle never self-certifies those consequences.
"""
