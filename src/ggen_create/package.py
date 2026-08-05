from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .cases import parameterize_body, parameterize_path, values_for
from .model import BuildResult, GgenCreateError, validate_identifier
from .session import admitted_files, load_session

PREFIX = "https://ggen.io/ontology/ggen-create#"
VARIABLES = [
    "name",
    "upper",
    "lower",
    "capitalized",
    "pascal",
    "camel",
    "snake",
    "upper_snake",
    "kebab",
    "title",
]
PACKAGE_RECEIPT_SCHEMA = "ggen-create-package-receipt/0.2"
PACKAGE_SCHEMA = "ggen-create-package/0.2"


def _turtle_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def ontology_text(value: str) -> str:
    values = values_for(value)
    predicates = []
    for variable in VARIABLES:
        suffix = ";" if variable != VARIABLES[-1] else "."
        predicates.append(
            f"    gc:{variable} {_turtle_literal(values[variable])} {suffix}"
        )
    return (
        f"@prefix gc: <{PREFIX}> .\n\n"
        "gc:subject a gc:GenerationSubject ;\n"
        + "\n".join(predicates)
        + "\n"
    )


def sparql_query() -> str:
    selected = " ".join("?" + variable for variable in VARIABLES)
    predicates = []
    for variable in VARIABLES:
        suffix = ";" if variable != VARIABLES[-1] else "."
        predicates.append(f"      gc:{variable} ?{variable} {suffix}")
    return (
        f"PREFIX gc: <{PREFIX}>\n"
        f"SELECT {selected}\n"
        "WHERE {\n"
        "  gc:subject a gc:GenerationSubject ;\n"
        + "\n".join(predicates)
        + "\n}"
    )


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _template_filename(index: int, rel: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in rel).strip("_")
    safe = safe[:72] or "file"
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:10]
    return f"{index:04d}-{safe}-{digest}.tmpl"


def _file_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _receipt_document(
    files: dict[str, bytes],
    *,
    operation: str,
    generator: str,
    parameter_value: str,
    parent: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": PACKAGE_RECEIPT_SCHEMA,
        "algorithm": "sha256",
        "operation": operation,
        "generator": generator,
        "parameter_value": parameter_value,
        "parent": parent,
        "files": {
            path: _file_hash(content)
            for path, content in sorted(files.items(), key=lambda item: item[0])
        },
    }
    return {
        **payload,
        "receipt_digest": _file_hash(_canonical_json(payload)),
    }


def _receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")


def _planned_files(session_path: Path) -> dict[str, bytes]:
    session = load_session(session_path)
    seed = session["templatize_using_name"]
    if not seed:
        raise GgenCreateError(
            "PARAMETER_NOT_SEEDED_REFUSED",
            "run 'ggen-create usename <value>'",
        )
    root = session_path.parent
    files = admitted_files(session_path)
    query = sparql_query()
    planned: dict[str, bytes] = {}
    # This is intentionally the frontmatter schema only. A project version is
    # a declarative-schema marker in ggen and makes the manifest ambiguous.
    planned["ggen.toml"] = (
        "[project]\n"
        f"name = {json.dumps(session['name'])}\n\n"
        "[ontology]\n"
        'source = "ontology.ttl"\n\n'
        "[templates]\n"
        'dir = "templates"\n'
    ).encode("utf-8")
    planned["ontology.ttl"] = ontology_text(seed).encode("utf-8")

    template_manifest: list[dict[str, Any]] = []
    for index, rel in enumerate(files):
        source = (root / rel).read_text(encoding="utf-8")
        target, path_replacements = parameterize_path(rel, seed)
        if session["gen_parent_dir"]:
            target = "{{ row.name }}/" + target
        body, body_replacements = parameterize_body(source, seed)
        query_indented = "\n".join("    " + line for line in query.splitlines())
        template = (
            "---\n"
            f"to: {_yaml_quote(target)}\n"
            "sparql:\n"
            "  entities: |\n"
            f"{query_indented}\n"
            "for_each: entities\n"
            "---\n"
            f"{body}"
        )
        filename = _template_filename(index, rel)
        planned[f"templates/{filename}"] = template.encode("utf-8")
        template_manifest.append(
            {
                "source": rel,
                "template": f"templates/{filename}",
                "target": target,
                "path_replacements": len(path_replacements),
                "content_replacements": len(body_replacements),
            }
        )

    metadata = {
        "schema": PACKAGE_SCHEMA,
        "generator": session["name"],
        "parameter": {"id": "name", "seed": seed, "value": seed},
        "gen_parent_dir": session["gen_parent_dir"],
        "files": template_manifest,
    }
    planned["ggen-create-package.json"] = json.dumps(
        metadata,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    receipt = _receipt_document(
        planned,
        operation="package-build",
        generator=session["name"],
        parameter_value=seed,
    )
    planned["receipt.json"] = _receipt_bytes(receipt)
    return planned


def _directory_matches(root: Path, planned: dict[str, bytes]) -> bool:
    actual = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return actual == planned


def _next_archive(target: Path) -> Path:
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def build_package(
    session_path: Path,
    output_root: Path,
    *,
    force: bool = False,
) -> BuildResult:
    session = load_session(session_path)
    planned = _planned_files(session_path)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / session["name"]
    archived: Path | None = None

    if target.exists():
        if _directory_matches(target, planned):
            return BuildResult(target, False, None, target / "receipt.json")
        if force:
            shutil.rmtree(target)
        else:
            archived = _next_archive(target)
            target.rename(archived)

    temp = Path(tempfile.mkdtemp(prefix=f".{session['name']}-", dir=output_root))
    try:
        for rel, content in planned.items():
            path = temp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        os.replace(temp, target)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        if archived is not None and not target.exists():
            archived.rename(target)
        raise
    return BuildResult(target, True, archived, target / "receipt.json")


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GgenCreateError(code, f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GgenCreateError(code, f"{path} must contain an object")
    return value


def _package_files(package_dir: Path) -> dict[str, bytes]:
    receipt_path = package_dir / "receipt.json"
    return {
        path.relative_to(package_dir).as_posix(): path.read_bytes()
        for path in sorted(package_dir.rglob("*"))
        if path.is_file() and path != receipt_path
    }


def rewrite_package_parameter(package_dir: Path, value: str) -> dict[str, Any]:
    value = validate_identifier(
        value,
        code="PARAMETER_VALUE_REFUSED",
        label="package parameter value",
    )
    package_dir = package_dir.resolve()
    from .integrity import verify_package

    before = verify_package(package_dir)
    if not before["valid"]:
        raise GgenCreateError(
            "PACKAGE_INTEGRITY_REFUSED",
            json.dumps(before, indent=2, sort_keys=True),
        )

    metadata_path = package_dir / "ggen-create-package.json"
    ontology_path = package_dir / "ontology.ttl"
    receipt_path = package_dir / "receipt.json"
    if not metadata_path.is_file():
        raise GgenCreateError(
            "PACKAGE_METADATA_MISSING_REFUSED",
            str(metadata_path),
        )
    metadata = _read_json_object(
        metadata_path,
        "PACKAGE_METADATA_PARSE_REFUSED",
    )
    if metadata.get("schema") != PACKAGE_SCHEMA:
        raise GgenCreateError(
            "PACKAGE_METADATA_SCHEMA_REFUSED",
            f"unsupported package schema: {metadata.get('schema')!r}",
        )
    parameter = metadata.get("parameter")
    if not isinstance(parameter, dict):
        raise GgenCreateError(
            "PACKAGE_METADATA_SCHEMA_REFUSED",
            str(metadata_path),
        )
    validate_identifier(
        parameter.get("seed"),
        code="PACKAGE_METADATA_SCHEMA_REFUSED",
        label="package parameter seed",
    )
    validate_identifier(
        parameter.get("value"),
        code="PACKAGE_METADATA_SCHEMA_REFUSED",
        label="existing package parameter value",
    )
    generator = validate_identifier(
        metadata.get("generator"),
        code="PACKAGE_METADATA_SCHEMA_REFUSED",
        label="package generator",
    )
    old_receipt = _read_json_object(
        receipt_path,
        "PACKAGE_RECEIPT_INVALID_REFUSED",
    )
    parent = old_receipt.get("receipt_digest")
    if not isinstance(parent, str):
        parent = _file_hash(_canonical_json(old_receipt))

    parameter["value"] = value
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    ontology_path.write_text(ontology_text(value), encoding="utf-8")
    receipt = _receipt_document(
        _package_files(package_dir),
        operation="parameter-rewrite",
        generator=generator,
        parameter_value=value,
        parent=parent,
    )
    receipt_path.write_bytes(_receipt_bytes(receipt))

    after = verify_package(package_dir)
    if not after["valid"]:
        raise GgenCreateError(
            "PACKAGE_REWRITE_INTEGRITY_REFUSED",
            json.dumps(after, indent=2, sort_keys=True),
        )
    return {
        "package": str(package_dir),
        "parameter_value": value,
        "parent": parent,
        "receipt_digest": receipt["receipt_digest"],
        "integrity": after,
    }
