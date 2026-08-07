#!/usr/bin/env python3
"""Close the real P7 parity crown: real `ggen` binary + real upstream `hygen` render.

`gall_ggen_binary_parity.py` (GB0-GB3) proved P0-P6 against a real `ggen` binary but
deliberately stopped short of P7 - that additionally requires a `reference_dir` produced
by the real upstream `hygen` render step (a separate npm package from `hygen-create`,
which only captures/templatizes, not renders). This script closes that gap for real:

  PC0 build hygen-create's CLI from the live submodule (hermetic yarn install/build,
      same fix as gall_submodule_parity.py's SM1 for the local yarn/corepack quirk)
  PC1 run `hygen-create generate` against the live submodule's already-captured example
      session, producing real `_templates/greeter/new/*.ejs.t` Hygen templates
  PC2 render the Hola variant with the real `hygen` renderer (`npx hygen greeter new
      --name Hola`) - a fresh, independent tool never previously exercised by this repo
  PC3 call `verify_parity` with that rendered tree as `reference_dir` against a real
      `ggen` binary, and assert `P7_PARITY_CROWN == "ALIVE"` with an exact,
      zero-drift `reference_comparison`

This is the actual `HYGEN_CREATE_PARITY_ALIVE` gate `product/PRD.md` describes. If any
checkpoint here fails, that's a real, typed finding to report and fix - not something to
force green.

Opt-in only: requires the `vendor/hygen-create` submodule, a real `ggen` binary on PATH
(or $GGEN_BIN), Node/npm/yarn, and network access (`npx hygen` fetches on first use). Not
part of the default GALL crown; wired into CI only on push to `main` (see
`.github/workflows/ci.yml`'s `p7-crown` job).

    python3 scripts/gall_p7_crown.py --root . --receipt p7-crown-receipt.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gall_hygen_parity import (  # noqa: E402
    ALIVE,
    BUILD_BROKEN,
    REFERENCE_COMMIT,
    UNSUPPORTED,
    GallFailure,
)
from ggen_create.session import add_paths, set_seed, start_session  # noqa: E402
from ggen_create.verify import verify_parity  # noqa: E402

SUBMODULE = Path("vendor/hygen-create")
SUBMODULE_EXAMPLE = SUBMODULE / "example"


def _run(command: list[str], cwd: Path, timeout: int = 300, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=merged_env,
    )


def _resolve_ggen_bin() -> str:
    ggen_bin = os.environ.get("GGEN_BIN", "ggen")
    resolved = shutil.which(ggen_bin)
    if resolved is None:
        raise FileNotFoundError(f"UNSUPPORTED:GGEN_EXECUTABLE_MISSING:{ggen_bin}")
    return resolved


def check_hygen_create_cli_builds(root: Path) -> dict[str, Any]:
    """PC0: build a working hygen-create CLI from the live submodule, hermetically."""
    submodule = root / SUBMODULE
    if not (submodule / "package.json").is_file():
        raise FileNotFoundError(
            "UNSUPPORTED:SUBMODULE_NOT_INITIALIZED:"
            "run `git submodule update --init vendor/hygen-create`"
        )
    yarn = shutil.which("yarn")
    npm = shutil.which("npm")
    if yarn is not None and (submodule / "yarn.lock").is_file():
        install_command = [yarn, "install"]
        build_command = [yarn, "run", "build"]
    elif npm is not None:
        install_command = [npm, "install", "--no-audit", "--no-fund"]
        build_command = [npm, "run", "build"]
    else:
        raise FileNotFoundError("UNSUPPORTED:NPM_EXECUTABLE_MISSING")
    # Hermetic /tmp copy: Yarn Classic's corepack-compat check walks up the directory
    # tree for the nearest package.json and can pick up an unrelated ancestor project's
    # "packageManager" field otherwise (same fix as gall_submodule_parity.py's SM1).
    hermetic_base = "/tmp" if Path("/tmp").is_dir() else None
    workdir_holder = tempfile.mkdtemp(prefix="ggen-create-p7-build-", dir=hermetic_base)
    workdir = Path(workdir_holder) / "hygen-create"
    shutil.copytree(submodule, workdir, ignore=shutil.ignore_patterns(".git", "node_modules", "dist"))
    for label, command in (("install", install_command), ("build", build_command)):
        completed = _run(command, cwd=workdir, timeout=300)
        if completed.returncode != 0:
            raise GallFailure(
                f"BUILD_BROKEN:HYGEN_CREATE_BUILD_FAILED:{label}:"
                + (completed.stderr.strip()[-2000:] or completed.stdout.strip()[-2000:])
            )
    cli_bin = workdir / "bin" / "hygen-create"
    if not cli_bin.is_file():
        raise GallFailure(f"BUILD_BROKEN:HYGEN_CREATE_CLI_MISSING:{cli_bin}")
    return {"workdir": str(workdir), "cli_bin": str(cli_bin)}


def check_templates_generated(root: Path) -> dict[str, Any]:
    """PC1: run hygen-create generate against the live submodule example."""
    build = check_hygen_create_cli_builds(root)
    cli_bin = build["cli_bin"]
    example_root = root / SUBMODULE_EXAMPLE
    hermetic_base = "/tmp" if Path("/tmp").is_dir() else None
    scratch = Path(tempfile.mkdtemp(prefix="ggen-create-p7-generate-", dir=hermetic_base))
    source = scratch / "greeter-source"
    templates_dir = scratch / "_templates"
    source.mkdir(parents=True)
    templates_dir.mkdir(parents=True)
    for relative in ("hygen-create.json", "package.json", "dist/hello.js"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((example_root / relative).read_bytes())
    node = shutil.which("node")
    if node is None:
        raise FileNotFoundError("UNSUPPORTED:NODE_EXECUTABLE_MISSING")
    completed = _run(
        [node, cli_bin, "generate"],
        cwd=source,
        env={"HYGEN_CREATE_TMPLS": str(templates_dir)},
        timeout=60,
    )
    if completed.returncode != 0:
        raise GallFailure(
            f"BUILD_BROKEN:TEMPLATE_GENERATION_FAILED:{completed.stderr.strip() or completed.stdout.strip()}"
        )
    produced = sorted(str(p.relative_to(templates_dir)) for p in templates_dir.rglob("*") if p.is_file())
    expected = sorted(
        str(Path("greeter/new") / name)
        for name in ("hygen-create.json.ejs.t", "package.json.ejs.t", "dist_hello.js.ejs.t")
    )
    if produced != expected:
        raise GallFailure(f"BUILD_BROKEN:TEMPLATE_SET_DRIFT:{produced!r}")
    return {"templates_dir": str(templates_dir), "produced": produced}


def check_hola_rendered_by_real_hygen(root: Path) -> dict[str, Any]:
    """PC2: render the Hola variant with the real, independent `hygen` renderer."""
    templates = check_templates_generated(root)
    templates_dir = templates["templates_dir"]
    npx = shutil.which("npx")
    if npx is None:
        raise FileNotFoundError("UNSUPPORTED:NPX_EXECUTABLE_MISSING")
    hermetic_base = "/tmp" if Path("/tmp").is_dir() else None
    rendered = Path(tempfile.mkdtemp(prefix="ggen-create-p7-render-", dir=hermetic_base))
    completed = _run(
        [npx, "hygen", "greeter", "new", "--name", "Hola"],
        cwd=rendered,
        env={"HYGEN_TMPLS": templates_dir},
        timeout=120,
    )
    if completed.returncode != 0:
        raise GallFailure(
            f"BUILD_BROKEN:HYGEN_RENDER_FAILED:{completed.stderr.strip() or completed.stdout.strip()}"
        )
    produced = sorted(str(p.relative_to(rendered)) for p in rendered.rglob("*") if p.is_file())
    expected = sorted(("hygen-create.json", "package.json", "dist/hola.js"))
    if produced != expected:
        raise GallFailure(f"BUILD_BROKEN:RENDERED_FILE_SET_DRIFT:{produced!r}")
    return {"rendered_dir": str(rendered), "produced": produced}


def check_p7_crown_alive(root: Path) -> dict[str, Any]:
    """PC3: call verify_parity against the real ggen binary and the real rendered tree."""
    ggen_bin = _resolve_ggen_bin()
    render = check_hola_rendered_by_real_hygen(root)
    example_root = root / SUBMODULE_EXAMPLE
    hermetic_base = "/tmp" if Path("/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="ggen-create-p7-verify-", dir=hermetic_base) as raw:
        session_root = Path(raw) / "session"
        session_root.mkdir()
        for relative in ("package.json", "dist/hello.js"):
            target = session_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((example_root / relative).read_bytes())
        session_path = start_session(session_root, "greeter")
        add_paths(session_path, ["package.json", "dist/hello.js"], cwd=session_root)
        set_seed(session_path, "Hello")
        report = verify_parity(
            session_path,
            output_root=Path(raw) / "verify",
            ggen_bin=ggen_bin,
            variation_value="Hola",
            sync_args=["sync", "run"],
            reference_dir=Path(render["rendered_dir"]),
            reference_id=REFERENCE_COMMIT,
        )
        if report["checkpoints"]["P7_PARITY_CROWN"] != ALIVE:
            raise GallFailure(
                f"BUILD_BROKEN:P7_NOT_ALIVE:{report['checkpoints']!r}:"
                f"{report.get('reference_comparison')!r}"
            )
        comparison = report["reference_comparison"]
        if not comparison or not comparison.get("equal"):
            raise GallFailure(f"BUILD_BROKEN:REFERENCE_COMPARISON_NOT_EQUAL:{comparison!r}")
        return {
            "checkpoints": report["checkpoints"],
            "reference_comparison": comparison,
            "report_path": report["report_path"],
        }


CHECKPOINTS: tuple[tuple[str, str, Callable[[Path], dict[str, Any]]], ...] = (
    ("PC0_HYGEN_CREATE_CLI_BUILDS", "build a working hygen-create CLI from the live submodule", check_hygen_create_cli_builds),
    ("PC1_TEMPLATES_GENERATED", "hygen-create generate produces real Hygen .ejs.t templates", check_templates_generated),
    ("PC2_HOLA_RENDERED_BY_REAL_HYGEN", "the real, independent hygen renderer produces the Hola variant", check_hola_rendered_by_real_hygen),
    ("PC3_P7_CROWN_ALIVE", "verify_parity reaches P7_PARITY_CROWN: ALIVE with zero-drift byte-exact comparison", check_p7_crown_alive),
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
        "schema": "ggen-create.gall.p7-crown.receipt.v1",
        "subject": {
            "repository": "seanchatmangpt/ggen-create",
            "submodule_path": str(SUBMODULE),
            "reference_commit": REFERENCE_COMMIT,
            "root": str(root),
        },
        "checkpoints": results,
        "failures": failures,
        "standing": standing,
        "claim_ceiling": "HYGEN_CREATE_PARITY_ALIVE" if standing == ALIVE else "NO_CLAIM",
        "note": (
            "PC0-PC3 close the real P7 parity crown: real ggen binary + real independent "
            "upstream hygen render, byte-exact comparison. This is the evidence "
            "product/PRD.md's HYGEN_CREATE_PARITY_ALIVE gate requires."
        ),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "replay": {
            "command": "python3 scripts/gall_p7_crown.py --root . --receipt p7-crown-receipt.json"
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
