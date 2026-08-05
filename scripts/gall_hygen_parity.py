#!/usr/bin/env python3
"""Execute Gall checkpoints binding ggen-create docs and examples to hygen-create."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REFERENCE_REPOSITORY = "ronp001/hygen-create"
REFERENCE_COMMIT = "124fac27df0ddbc498b841ba3e05997ed10e4c39"
REFERENCE_TREE = "bf088a9e2ab533cd9ba035ecddb0c31f30e292bd"
ALIVE = "ALIVE"
BUILD_BROKEN = "BUILD_BROKEN"
UNSUPPORTED = "UNSUPPORTED"


class GallFailure(RuntimeError):
    """A falsified checkpoint with a stable diagnostic."""


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_words(value: str) -> list[str]:
    normalized = re.sub(r"[-_\s]+", " ", value.strip())
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized)
    words = [part.lower() for part in normalized.split() if part]
    if not words:
        raise GallFailure(f"REFUSED:EMPTY_CASE_SEED:{value!r}")
    return words


def _forms(value: str) -> dict[str, str]:
    words = _split_words(value)
    pascal = "".join(word.capitalize() for word in words)
    return {
        "upper_snake": "_".join(words).upper(),
        "snake": "_".join(words),
        "kebab": "-".join(words),
        "pascal": pascal,
        "camel": words[0] + "".join(word.capitalize() for word in words[1:]),
        "upper": "".join(words).upper(),
        "capitalized": "".join(words).capitalize(),
        "lower": "".join(words),
    }


def transform_text(text: str, seed: str, target: str) -> str:
    """Apply the original family of case transforms with its left boundary rule."""
    source = _forms(seed)
    destination = _forms(target)
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in ("upper_snake", "snake", "kebab", "pascal", "camel", "upper", "capitalized", "lower"):
        candidate = source[key]
        if candidate in seen:
            continue
        seen.add(candidate)
        pairs.append((candidate, destination[key]))
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    rendered = text
    for old, new in pairs:
        rendered = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}", lambda _: new, rendered)
    return rendered


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def manufacture(reference_root: Path, output_root: Path, target: str) -> dict[str, Any]:
    """Construct a deterministic greeter projection without ambient execution."""
    capture = json.loads((reference_root / "hygen-create.json").read_text(encoding="utf-8"))
    seed = capture["templatize_using_name"]
    output_root.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    for source_path in capture["files_and_dirs"]:
        source = reference_root / source_path
        if not source.is_file():
            raise GallFailure(f"BUILD_BROKEN:CAPTURE_FILE_MISSING:{source_path}")
        target_path = transform_text(source_path, seed, target)
        destination = output_root / target_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            transform_text(source.read_text(encoding="utf-8"), seed, target),
            encoding="utf-8",
        )
        produced.append(target_path)
    return {
        "seed": seed,
        "target": target,
        "files": sorted(produced),
        "tree_sha256": tree_digest(output_root),
    }


def execute_example(output_root: Path) -> dict[str, Any]:
    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("UNSUPPORTED:NPM_EXECUTABLE_MISSING")
    started = time.monotonic()
    completed = subprocess.run(
        [npm, "run", "hola", "--silent"],
        cwd=output_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        raise GallFailure(
            "BUILD_BROKEN:GREETER_EXECUTION_FAILED:"
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    if completed.stdout.strip() != "Hola!":
        raise GallFailure(
            f"BUILD_BROKEN:GREETER_STDOUT_DRIFT:{completed.stdout.strip()!r}"
        )
    return {
        "command": "npm run hola --silent",
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "elapsed_ms": elapsed_ms,
    }


def _load_manifest(root: Path) -> tuple[Path, dict[str, Any]]:
    reference_root = root / "examples" / "hygen-create-reference"
    manifest_path = reference_root / "parity.json"
    if not manifest_path.is_file():
        raise GallFailure("BUILD_BROKEN:REFERENCE_MANIFEST_MISSING")
    return reference_root, json.loads(manifest_path.read_text(encoding="utf-8"))


def check_reference_identity(root: Path) -> dict[str, Any]:
    _, manifest = _load_manifest(root)
    reference = manifest["reference"]
    observed = (
        reference.get("repository"),
        reference.get("commit"),
        reference.get("tree"),
    )
    expected = (REFERENCE_REPOSITORY, REFERENCE_COMMIT, REFERENCE_TREE)
    if observed != expected:
        raise GallFailure(f"BUILD_BROKEN:REFERENCE_IDENTITY_DRIFT:{observed!r}")
    return {
        "repository": reference["repository"],
        "commit": reference["commit"],
        "tree": reference["tree"],
    }


def check_reference_blobs(root: Path) -> dict[str, Any]:
    reference_root, manifest = _load_manifest(root)
    evidence: dict[str, Any] = {}
    for relative, expected in sorted(manifest["files"].items()):
        path = reference_root / relative
        if not path.is_file():
            raise GallFailure(f"BUILD_BROKEN:REFERENCE_FILE_MISSING:{relative}")
        data = path.read_bytes()
        actual = _git_blob_sha(data)
        if actual != expected:
            raise GallFailure(
                f"BUILD_BROKEN:REFERENCE_BLOB_DRIFT:{relative}:{expected}:{actual}"
            )
        evidence[relative] = {"git_blob": actual, "sha256": _sha256(data), "bytes": len(data)}
    return evidence


def check_capture_contract(root: Path) -> dict[str, Any]:
    reference_root, manifest = _load_manifest(root)
    capture = json.loads((reference_root / "hygen-create.json").read_text(encoding="utf-8"))
    contract = manifest["capture"]
    if list(capture) != contract["ordered_fields"]:
        raise GallFailure("BUILD_BROKEN:CAPTURE_FIELD_ORDER_DRIFT")
    if capture["name"] != contract["generator"]:
        raise GallFailure("BUILD_BROKEN:CAPTURE_GENERATOR_DRIFT")
    if capture["templatize_using_name"] != contract["seed"]:
        raise GallFailure("BUILD_BROKEN:CAPTURE_SEED_DRIFT")
    if list(capture["files_and_dirs"]) != contract["included"]:
        raise GallFailure("BUILD_BROKEN:CAPTURE_FILE_SET_DRIFT")
    if capture["gen_parent_dir"] is not contract["gen_parent_dir"]:
        raise GallFailure("BUILD_BROKEN:CAPTURE_PARENT_POLICY_DRIFT")
    return {
        "ordered_fields": list(capture),
        "generator": capture["name"],
        "seed": capture["templatize_using_name"],
        "included": list(capture["files_and_dirs"]),
        "gen_parent_dir": capture["gen_parent_dir"],
    }


def check_case_corpus(root: Path) -> dict[str, Any]:
    reference_root, _ = _load_manifest(root)
    corpus = json.loads((reference_root / "test_strings.json").read_text(encoding="utf-8"))
    checked = 0
    sections: dict[str, int] = {}
    for section_name, section in corpus.items():
        if section_name.startswith("about "):
            continue
        seed = section["defs"]["hygen-create usename"]
        target = section["defs"]["hygen --name"]
        section_count = 0
        for case_name, values in section["comparisons"].items():
            source, expected = values[:2]
            actual = transform_text(source, seed, target)
            if actual != expected:
                raise GallFailure(
                    f"BUILD_BROKEN:CASE_CORPUS_DRIFT:{section_name}:{case_name}:{expected!r}:{actual!r}"
                )
            checked += 1
            section_count += 1
        sections[section_name] = section_count
    return {"comparisons": checked, "sections": sections}


def check_documentation(root: Path) -> dict[str, Any]:
    _, manifest = _load_manifest(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    guide = (root / "docs" / "hygen-create-parity.md").read_text(encoding="utf-8")
    combined = readme + "\n" + guide
    missing = [
        item
        for item in (
            *manifest["documentation"]["required_commands"],
            *manifest["documentation"]["required_facts"],
        )
        if item not in combined
    ]
    if missing:
        raise GallFailure(f"BUILD_BROKEN:DOCUMENTATION_DRIFT:{missing!r}")
    if REFERENCE_COMMIT not in combined or REFERENCE_TREE not in combined:
        raise GallFailure("BUILD_BROKEN:DOCUMENTATION_REFERENCE_IDENTITY_MISSING")
    return {
        "commands": manifest["documentation"]["required_commands"],
        "facts": manifest["documentation"]["required_facts"],
        "reference_commit": REFERENCE_COMMIT,
        "reference_tree": REFERENCE_TREE,
    }


def check_reconstruction(root: Path) -> dict[str, Any]:
    reference_root, _ = _load_manifest(root)
    with tempfile.TemporaryDirectory(prefix="ggen-create-reconstruct-") as raw:
        output = Path(raw)
        result = manufacture(reference_root, output, "Hello")
        for relative in ("hygen-create.json", "package.json", "dist/hello.js"):
            if (output / relative).read_bytes() != (reference_root / relative).read_bytes():
                raise GallFailure(f"BUILD_BROKEN:RECONSTRUCTION_DRIFT:{relative}")
        return result


def check_variation(root: Path) -> dict[str, Any]:
    reference_root, _ = _load_manifest(root)
    with tempfile.TemporaryDirectory(prefix="ggen-create-variation-") as raw:
        output = Path(raw)
        result = manufacture(reference_root, output, "Hola")
        package = json.loads((output / "package.json").read_text(encoding="utf-8"))
        capture = json.loads((output / "hygen-create.json").read_text(encoding="utf-8"))
        expected_files = ["dist/hola.js", "hygen-create.json", "package.json"]
        if result["files"] != expected_files:
            raise GallFailure(f"BUILD_BROKEN:VARIATION_FILE_SET_DRIFT:{result['files']!r}")
        if package["name"] != "hola" or package["scripts"] != {"hola": "node dist/hola.js"}:
            raise GallFailure("BUILD_BROKEN:VARIATION_PACKAGE_DRIFT")
        if capture["templatize_using_name"] != "Hola":
            raise GallFailure("BUILD_BROKEN:VARIATION_CAPTURE_SEED_DRIFT")
        if list(capture["files_and_dirs"]) != ["hygen-create.json", "package.json", "dist/hola.js"]:
            raise GallFailure("BUILD_BROKEN:VARIATION_CAPTURE_FILE_SET_DRIFT")
        result["execution"] = execute_example(output)
        return result


def check_replay(root: Path) -> dict[str, Any]:
    reference_root, _ = _load_manifest(root)
    with tempfile.TemporaryDirectory(prefix="ggen-create-replay-a-") as left_raw, tempfile.TemporaryDirectory(prefix="ggen-create-replay-b-") as right_raw:
        left = manufacture(reference_root, Path(left_raw), "Hola")
        right = manufacture(reference_root, Path(right_raw), "Hola")
        if left["tree_sha256"] != right["tree_sha256"]:
            raise GallFailure("BUILD_BROKEN:DETERMINISTIC_REPLAY_DRIFT")
        return {
            "first_tree_sha256": left["tree_sha256"],
            "second_tree_sha256": right["tree_sha256"],
            "changed_revision_policy": "no changed revision for identical tree; archive as greeter.1 only after drift",
        }


CHECKPOINTS: tuple[tuple[str, str, Callable[[Path], dict[str, Any]]], ...] = (
    ("G0_REFERENCE_IDENTITY", "preserve exact upstream subject", check_reference_identity),
    ("G1_REFERENCE_BLOBS", "preserve canonical example bytes", check_reference_blobs),
    ("G2_CAPTURE_CONTRACT", "admit session shape and file set", check_capture_contract),
    ("G3_CASE_CORPUS", "close lexical unit transformations", check_case_corpus),
    ("G4_DOCUMENTATION", "bind documented commands and consequences", check_documentation),
    ("G5_RECONSTRUCTION", "reconstruct the Hello exemplar byte-exactly", check_reconstruction),
    ("G6_VARIATION_CONSEQUENCE", "manufacture and execute the Hola variation", check_variation),
    ("G7_REPLAY_CROWN", "prove deterministic replay and revision law", check_replay),
)


def run_checkpoints(root: Path) -> dict[str, Any]:
    root = root.resolve()
    started = time.monotonic()
    results: dict[str, Any] = {}
    failures: list[str] = []
    for checkpoint_id, purpose, function in CHECKPOINTS:
        checkpoint_started = time.monotonic()
        try:
            evidence = function(root)
            state = ALIVE
            failure = None
        except FileNotFoundError as exc:
            evidence = {}
            state = UNSUPPORTED
            failure = str(exc)
            failures.append(f"{checkpoint_id}:{failure}")
        except Exception as exc:  # receipt every failed boundary
            evidence = {}
            state = BUILD_BROKEN
            failure = str(exc)
            failures.append(f"{checkpoint_id}:{failure}")
        results[checkpoint_id] = {
            "purpose": purpose,
            "standing": state,
            "elapsed_ms": round((time.monotonic() - checkpoint_started) * 1000),
            "failure": failure,
            "evidence": evidence,
        }
    standing = ALIVE if not failures else BUILD_BROKEN
    return {
        "schema": "ggen-create.gall.hygen-parity.receipt.v1",
        "subject": {
            "repository": "seanchatmangpt/ggen-create",
            "reference_repository": REFERENCE_REPOSITORY,
            "reference_commit": REFERENCE_COMMIT,
            "reference_tree": REFERENCE_TREE,
            "root": str(root),
        },
        "pipeline": [
            "parse",
            "route",
            "admit_or_refuse",
            "construct",
            "actuate_in_temporary_boundary",
            "observe_consequence",
            "verify",
            "receipt",
            "replay",
            "standing",
        ],
        "checkpoints": results,
        "failures": failures,
        "standing": standing,
        "claim_ceiling": "EXAMPLE_DOCUMENTATION_AND_LOCAL_REFERENCE_CONSEQUENCE_ONLY",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "replay": {
            "command": "python3 scripts/gall_hygen_parity.py --root . --receipt gall-hygen-parity-receipt.json"
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--receipt", default="")
    args = parser.parse_args(argv)
    receipt = run_checkpoints(Path(args.root))
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if receipt["standing"] == ALIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
