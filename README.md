# ggen-create

Create deterministic ggen manufacturing packages from existing working examples.

## Rust DSPy reasoning substrate

`crates/ggen-dspy` is the authority-safe Rust reasoning and optimization kernel recovered from the historical `ggen-dspy` lineage. It provides typed signatures/modules, Predict/Chain of Thought, ReAct, retrieval and multi-hop patterns, Program of Thought, few-shot/MIPRO-style optimization, evaluation, assertions, adapters, context/cache/usage, and reusable agent patterns.

Its enterprise boundary is intentional: **SELECT / CONSTRUCT is allowed; ambient DO is not**. ReAct manufactures `ActionIntent`; Program of Thought manufactures `CodeIntent`; the host broker owns policy, credentials, actuation, receipts, replay, and standing. The crate is publish-disabled, forbids unsafe Rust, and has zero runtime dependencies at the admitted architecture revision.

Architecture and operating evidence:

- [authoritative ARD](architecture/ARD.md)
- [Rust DSPy authority ADR](architecture/ADR-0001-RUST-DSPY-AUTHORITY.md)
- [enterprise target architecture](architecture/ENTERPRISE_ARCHITECTURE.md)
- [`enterprise.toml` executable architecture contract](architecture/enterprise.toml)
- [enterprise readiness gates](docs/ENTERPRISE_READINESS.md)

The architecture contract is executable through `scripts/enterprise_architecture_check.py`; its positive and negative falsifier tests run in the repository build evidence path.

## Hygen-create parity contract

The first Gall checkpoint is the canonical `hygen-create` greeter example, preserved byte-for-byte from `ronp001/hygen-create@124fac27df0ddbc498b841ba3e05997ed10e4c39` (tree `bf088a9e2ab533cd9ba035ecddb0c31f30e292bd`). The ggen-create documentation uses the same files, capture lifecycle, case-family expectations, variation, executable behavior, and revision law.

```text
hygen-create: exemplar -> Hygen generator -> generated project
ggen-create:  exemplar -> ggen package    -> generated project
```

The command correspondence is intentionally direct:

| Hygen reference | ggen-create contract |
| --- | --- |
| `hygen-create start greeter` | `ggen-create start greeter` |
| `hygen-create add package.json dist/hello.js` | `ggen-create add package.json dist/hello.js` |
| `hygen-create usename Hello` | `ggen-create usename Hello` |
| `hygen-create status` | `ggen-create status` |
| `hygen-create generate` | `ggen-create generate` |
| `hygen greeter new --name Hola` | `ggen greeter new --name Hola` |

The admitted variation must create `dist/hola.js`, update the package script, and make `npm run hola` print `Hola!`.

Run the local crown:

```sh
python3 scripts/gall_hygen_parity.py --root . --receipt gall-hygen-parity-receipt.json
python3 -m unittest discover -s tests -p 'test_parity_*.py' -v
python3 scripts/enterprise_architecture_check.py --root . --receipt enterprise-architecture-receipt.json
```

Optionally, corroborate against a live vendored copy of upstream `hygen-create`
(requires network/Node/npm; see [live submodule validation](docs/hygen-create-parity.md#live-submodule-validation-opt-in)):

```sh
git submodule update --init vendor/hygen-create
python3 scripts/gall_submodule_parity.py --root . --receipt submodule-parity-receipt.json
```

See [the complete parity guide](docs/hygen-create-parity.md), [CI evidence architecture](docs/ci.md), [product requirements](product/PRD.md), and [architecture requirements](architecture/ARD.md).

## Standing

```text
reference identity and fixture bytes:       ALIVE
case-family unit contract:                  ALIVE
example reconstruction and variation:      ALIVE
documentation-to-example closure:           ALIVE
ggen-create CLI and package runtime:        ALIVE (local unit evidence)
real public ggen parity crown (P7):         ALIVE (real ggen + real upstream hygen render,
                                               exact-head CI: scripts/gall_p7_crown.py, run
                                               31216549992)
minimal agent topology (Phase 5):           ALIVE (real typed artifacts + decision logic,
                                               held-out replay: src/ggen_create/topology.py)
Rust DSPy implementation:                  ALIVE when exact-head Rust/build evidence is green
Rust DSPy enterprise architecture:         ADMITTED; executable conformance required for ALIVE
production workload standing:              NOT INFERRED from repository standing
```

`HYGEN_CREATE_PARITY_ALIVE` is admitted: `real ggen 26.8.6` reconstructs `Hello` and
generates `Hola`, the real, independent upstream `hygen` renderer generates `Hola` for
cross-rail comparison, and the two are byte-exact with zero drift — published under
exact-head CI on push to `main` (`.github/workflows/ci.yml`'s `p7-crown` job). See
`docs/hygen-create-parity.md`'s "Real P7 crown" section.

Install and run locally:

```sh
python3 -m pip install -e .
ggen-create --help
ggen-create start greeter
ggen-create add package.json dist/hello.js
ggen-create usename Hello
ggen-create status
ggen-create generate --output /tmp/packages
```
