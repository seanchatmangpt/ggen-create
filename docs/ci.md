# CI evidence architecture

`ggen-create` uses an 80/20 ERRC topology: every candidate receives one dependency-light exact-head admission, while path-owned deep evidence runs only for paths that can invalidate it.

## Universal admission

`.github/workflows/ci.yml` checks out the exact event head, verifies the observed Git `HEAD`, discovers changes from the exact admitted base, runs router and GALL contract tests, parses changed structured files, validates the bootstrap repository shape, emits typed failures, and uploads `ggen-create.ci.errc.receipt.v2`.

The admission receipt claim ceiling is `EXACT_HEAD_FAST_AUTHORITY_AND_ROUTING_ONLY`. It does not promote a skipped path-owned lane into successful evidence.

## GALL crown

Every candidate also runs one bounded GALL crown job containing eight explicit checkpoints: `exact_head`, `clean_tree`, `routing`, `ci`, `docs`, `ontology`, `build`, and `receipt`. Each checkpoint must transition `CANDIDATE → ADMITTED → ALIVE` and carries a positive witness, an executing negative falsifier, deterministic seed `0`, subprocess replay, exact revision, clean checkout, typed failure, owner, and claim ceiling.

The single runner writes one receipt per checkpoint plus an aggregate crown. The crown is `ALIVE` only when every checkpoint is independently `ALIVE`. Path-owned jobs may still be skipped when no owned path changed; those skips are routing decisions, not checkpoint evidence.

## Owned lanes

| Lane | Owned surfaces |
| --- | --- |
| `ci_deep` | `.github/**`, `scripts/ci_*.py`, `scripts/gall_*.py`, `scripts/enterprise_architecture_check.py`, `tests/test_ci_*.py`, `docs/ci.md`, `docs/gall.md` |
| `docs_deep` | `README.md`, `BOOTSTRAP.md`, `docs/**`, `product/**`, `architecture/**`, Markdown files |
| `ontology_deep` | `ontology/**` |
| `build_deep` | Cargo/toolchain files, `src/**`, `crates/**`, non-CI tests, examples, benches, fixtures, `architecture/enterprise.toml`, `scripts/enterprise_architecture_check.py`, and unknown future surfaces |

Workflow-only changes do not masquerade as product or ontology changes. Unknown future surfaces conservatively route to build evidence until ownership is made explicit. The enterprise architecture contract is deliberately docs+build owned; the checker that enforces it is deliberately CI+build owned. A policy change therefore cannot be admitted as prose-only or as CI-only evidence.

## Enterprise architecture conformance

When `build_deep` runs, `scripts/ci_admit.py --lane build` executes `scripts/enterprise_architecture_check.py` as the named `enterprise_architecture` check before product and Rust tests. The checker validates the admitted `architecture/enterprise.toml` contract, including:

- Rust DSPy component and required architecture documents are present;
- the toolchain is pinned and the lockfile is present;
- `ggen-dspy` remains publish-disabled;
- the admitted runtime dependency count remains zero;
- required authority markers remain present;
- prohibited ambient process/filesystem/network/FFI/unsafe markers remain absent;
- the host broker remains the exclusive external DO owner and model output remains non-authoritative.

The check emits `enterprise-architecture-receipt.json`. CI uploads that receipt as an exact-head workflow artifact. `tests/test_enterprise_architecture.py` includes a negative falsifier that injects `std::process::Command` into a fixture and requires conformance standing to collapse to `BUILD_BROKEN`.

Failure type:

```text
BUILD_BROKEN:ENTERPRISE_ARCHITECTURE_CONFORMANCE_FAILED
```

This is repository architecture standing only. It does not infer workload integration, environment, release, or production standing; those gates are defined in `docs/ENTERPRISE_READINESS.md`.

## Local replay

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests -p 'test_ci_*.py'
python3 -m py_compile scripts/ci_router.py scripts/ci_admit.py scripts/gall_contract.py scripts/gall_surfaces.py scripts/gall_checkpoint.py scripts/enterprise_architecture_check.py tests/test_ci_router.py tests/test_ci_gall.py
python3 scripts/enterprise_architecture_check.py --root . --receipt /tmp/enterprise-architecture-receipt.json
ruby -e "require 'yaml'; YAML.parse_file(ARGV.fetch(0))" .github/workflows/ci.yml
HEAD_SHA="$(git rev-parse HEAD)"
BASE_SHA="$(git rev-parse HEAD^)"
python3 scripts/ci_admit.py --base "$BASE_SHA" --head "$HEAD_SHA" --receipt /tmp/ci-errc-receipt.json
python3 scripts/gall_checkpoint.py --checkpoint all --base "$BASE_SHA" --head "$HEAD_SHA" --receipt /tmp/gall-crown.json
```

## Hygen parity Gall crown

Documentation and example changes are not admitted by UTF-8 checks alone. When `scripts/gall_hygen_parity.py` is present:

- `docs_deep` executes the G0–G7 crown so prose cannot drift from the pinned example;
- `build_deep` executes the enterprise architecture check, Python package (`pip install -e .`, full unit suite), Rust format/tests when a Cargo workspace is present, `tests/test_parity_*.py`, and the hygen parity crown;
- both lanes manufacture `gall-hygen-parity-receipt.json` with the pinned reference identity, checkpoint evidence, executable Hola consequence, replay digest, failures, and claim ceiling.

Local replay:

```sh
python3 scripts/ci_admit.py --lane docs
python3 scripts/ci_admit.py --lane build
python3 scripts/gall_hygen_parity.py --root . --receipt gall-hygen-parity-receipt.json
```

## P7 parity crown (push-to-main only)

`.github/workflows/ci.yml`'s `p7-crown` job closes the real `HYGEN_CREATE_PARITY_ALIVE` gate:
real `ggen` binary + real, independent upstream `hygen` render, byte-exact comparison
(`scripts/gall_p7_crown.py`, checkpoints PC0–PC3 — see `docs/hygen-create-parity.md`).

Unlike every other job above, this one runs only on `push` to `main`, not on every PR — it
downloads a pinned `ggen` release binary from `seanchatmangpt/ggen` (checksum-verified) and
does a full Node/npm/yarn install to drive the real `hygen` renderer, real network/time cost
that would otherwise slow every PR. It re-certifies the crown whenever `main` actually
changes, uploading `p7-crown-receipt.json` as a workflow artifact.

Local replay:

```sh
git submodule update --init vendor/hygen-create
python3 scripts/gall_p7_crown.py --root . --receipt p7-crown-receipt.json
```
