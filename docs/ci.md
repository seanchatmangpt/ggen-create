# CI evidence architecture

`ggen-create` uses an 80/20 ERRC topology: every candidate receives one dependency-light exact-head admission, while deeper evidence runs only for paths that can invalidate it.

## Universal admission

`.github/workflows/ci.yml` checks out the exact event head, verifies the observed Git `HEAD`, discovers changes from the exact admitted base, runs router self-tests, parses changed structured files, validates the bootstrap repository shape, emits typed failures, and uploads `ggen-create.ci.errc.receipt.v1`.

The receipt claim ceiling is `EXACT_HEAD_FAST_AUTHORITY_AND_ROUTING_ONLY`. It does not promote a skipped deep lane into successful evidence.

## Owned lanes

| Lane | Owned surfaces |
| --- | --- |
| `ci_deep` | `.github/**`, `scripts/ci_*.py`, `tests/test_ci_*.py`, `docs/ci.md` |
| `docs_deep` | `README.md`, `BOOTSTRAP.md`, `docs/**`, Markdown files |
| `ontology_deep` | `ontology/**` |
| `build_deep` | Cargo/toolchain files, `src/**`, `crates/**`, non-CI tests, examples, benches, fixtures, and unknown future surfaces |

Workflow-only changes do not masquerade as product or ontology changes. Unknown future surfaces conservatively route to build evidence until ownership is made explicit.

## Local replay

```sh
python3 -m unittest discover -s tests -p 'test_ci_*.py'
python3 -m py_compile scripts/ci_router.py scripts/ci_admit.py tests/test_ci_router.py
ruby -e "require 'yaml'; YAML.parse_file(ARGV.fetch(0))" .github/workflows/ci.yml
python3 scripts/ci_router.py --changed-file .github/workflows/ci.yml --changed-file docs/ci.md
```
