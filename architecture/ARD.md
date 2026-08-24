# Architecture Requirements and Design

## Product

`ggen-create`

## Version

`v26.8.7`

## Status

Architecture authority admitted. Documentation parity rail implemented. Product runtime (CLI and package build) admitted on `main` with local unit evidence. The external P7 crown against a real `ggen` binary and upstream `hygen-create` render is `ALIVE`, published under exact-head CI (`.github/workflows/ci.yml`'s `p7-crown` job, push-to-main). The minimal agent topology (`receiver`/`correspondence-analyst`/`admission-referee`) is `ALIVE` with held-out replay evidence — see "Handoff topology" below. The Rust DSPy capability is admitted as a CONSTRUCT-only reasoning substrate; its machine-readable enterprise authority contract is `architecture/enterprise.toml` and its decision record is ADR-0001.

## Document law

This ARD is the architecture authority for `ggen-create v26.8.7`. It binds system boundaries, component responsibilities, object model, security refusals, and determinism law. Product behavior is normative in `product/PRD.md`; this document explains how that behavior is manufactured and verified. `architecture/enterprise.toml` is the executable contract for the Rust DSPy authority boundary and may narrow, but may not silently widen, the authority granted by this ARD. Sentences elsewhere in this document scoped to a specific prior version (e.g. "v26.8.6 does not admit skills or agents") are that version's historical record and are not rewritten by later releases — later sections state the current, superseding standing explicitly.

## System boundary

`ggen-create` is a reverse compiler.

```text
working exemplars
→ admitted observation graph
→ candidate correspondences
→ admitted manufacturing graph
→ ggen package
```

It is not the runtime manufacturer of target artifacts.

```text
┌───────────────────┐
│ Working exemplars │
└─────────┬─────────┘
          │ observe
┌─────────▼─────────┐
│    ggen-create    │
│ SELECT / CONSTRUCT│
└─────────┬─────────┘
          │ admitted package
┌─────────▼─────────┐
│       ggen        │
│ deterministic DO  │
└─────────┬─────────┘
          │ artifacts + receipts
┌─────────▼─────────┐
│ verifier / mfact  │
└───────────────────┘
```

### Create-time vs construct-time fence

| Side | Product | Authority |
| --- | --- | --- |
| create-time | `ggen-create` | observation, inference, inspection, admission, packaging, verification intent |
| construct-time | `ggen` | deterministic manufacture from admitted package inputs |

Verification may subprocess public `ggen` inside isolated staging. That actuation is BRCE-bounded verification, not an embedded construction engine.

## v26.8.6 architecture scope

### In scope

| Layer | Admission |
| --- | --- |
| authority documents | PRD, ARD, roadmap, CLI contract law |
| repository evidence | ERRC admission, GALL crown, path-owned lanes |
| documentation parity rail | `scripts/gall_hygen_parity.py`, reference fixture, G0–G7 |
| Phase 1 runtime specification | capture, lexical inference, inspect, package, verify modules |
| capture schema | six-field session compatible with hygen-create |
| case-family engine | 24-comparison corpus and left-boundary law |
| package emission law | templates, SPARQL queries, revision archive |
| parity verification law | P0–P7 checkpoints and `parity-report.json` |

### Out of scope

| Layer | Deferred |
| --- | --- |
| structural anti-unification | Tree-sitter per-language admission |
| ~~multi-parameter collision law (multiple seeds + overlapping-occurrence detection)~~ | **ADMITTED, v26.8.7** — see "Correspondence engine — Phase 2" below. Declared constants, transform ambiguity beyond cross-seed overlap, binary/opaque-copy policy, and the `MULTI_PARAMETER_PARITY_ALIVE` exit gate remain deferred within Phase 2 |
| multi-exemplar variation axes | Phase 4 |
| skills and agents (full topology, 6 remaining agents) | Phase 6+ |
| ~~minimal agent topology (receiver/correspondence-analyst/admission-referee)~~ | **ADMITTED, v26.8.7** |
| MCP / A2A native runtime | post parity GA |
| automatic / autonomic controllers | post parity GA |
| `ggen-legacy` enterprise specialization | Phase 8 |

## Major components

### Capture engine

Responsibilities:

- root fencing;
- explicit include and exclude;
- file and tree hashing;
- symlink and binary classification;
- parser outcome recording;
- immutable subject identity.

v26.8.6 implementation module: `session.py`

Refusals:

```text
CAPTURE_ROOT_MISSING_REFUSED
SESSION_IN_PROGRESS_REFUSED
PATH_MISSING_REFUSED
PATH_OUTSIDE_CAPTURE_ROOT_REFUSED
SYMLINK_REFUSED
BINARY_FILE_REFUSED
NON_UTF8_FILE_REFUSED
```

Session manifest retains the original field order:

```json
{
  "about": "...",
  "hygen_create_version": "0.2.0",
  "name": "<generator>",
  "files_and_dirs": {},
  "templatize_using_name": null,
  "gen_parent_dir": false
}
```

The capture file location defines the capture root. The session file is included in generated output, matching the original iterative-generator workflow.

### Correspondence engine

Tiers:

1. deterministic lexical anti-unification — **v26.8.6**
2. Tree-sitter structural anti-unification — deferred
3. multi-exemplar variation-axis inference — deferred

All output is candidate evidence until admitted.

v26.8.6 implementation modules: `cases.py`, `inspect.py`

Lexical transform set for seed `HelloWorld`:

| Form | Value |
| --- | --- |
| `upper` | `HELLOWORLD` |
| `lower` | `helloworld` |
| `capitalized` | `HelloWorld` |
| `pascal` | `HelloWorld` |
| `camel` | `helloWorld` |
| `snake` | `hello_world` |
| `upper_snake` | `HELLO_WORLD` |
| `kebab` | `hello-world` |

Duplicate lexical values resolve by the original priority order:

```text
upper_snake → snake → kebab → pascal → camel → upper → capitalized → lower
```

Occurrences require start-of-string or a non-alphanumeric left neighbor.

### Correspondence engine — Phase 2: multiple seeds

Extends the capture engine's session manifest with a session-format version bump, not a
breaking change to the existing `v26.8.6` six-field shape: a session stays at
`hygen_create_version "0.4.0"` (the current `v26.8.6` format) until a second seed is added,
at which point it is migrated in place to `"0.5.0"` and gains a seventh field:

```json
{
  "about": "...",
  "hygen_create_version": "0.5.0",
  "name": "<generator>",
  "files_and_dirs": {},
  "templatize_using_name": "HelloWorld",
  "gen_parent_dir": false,
  "seeds": [
    {"name": "name", "value": "HelloWorld"},
    {"name": "greeting", "value": "Bonjour"}
  ]
}
```

`templatize_using_name` remains present and authoritative for `"0.4.0"` (single-seed)
sessions; for `"0.5.0"` sessions it is kept in sync with `seeds[0]` (the seed named `name`)
purely for read-compatibility with tooling that only knows the six-field shape — the `seeds`
list is authoritative once present.

v26.8.7 (Phase 2) implementation module: `session.py::add_seed`, `session.py::seeds_for_session`

Variable-namespace rule: the seed named `name` keeps the unprefixed `row.<transform>` Tera
bindings `v26.8.6` already defines (`row.pascal`, `row.snake`, ...); every other seed's ten
transform forms are scoped under its own name (`row.<seed_name>_<transform>`, e.g.
`row.greeting_pascal`) so two seeds' bindings can never collide with each other by name.

Overlapping-occurrence detection: the combined scan (`cases.py::replacements_for_many`) walks
all seeds' transform literals together. Two DIFFERENT seeds whose matched literals would
produce overlapping (not merely adjacent) spans in the same text is refused
(`PARAMETER_COLLISION_REFUSED`, already declared below but unimplemented before this phase) —
never silently resolved by preferring one seed's match over the other's. A single seed's own
internal duplicate-literal resolution (the existing priority order above) is unchanged.

v26.8.7 implementation modules: `cases.py`, `package.py`, `inspect.py` — the
`session["templatize_using_name"]` + `parameterize_body`/`parameterize_path`/`render_concrete`
call sites in these two modules switched to `seeds_for_session(session)` + the corresponding
`_many` function, so a two-seed session actually flows through capture, `status`, and package
build (`ontology.ttl`/SPARQL query gain one qualified predicate set per additional seed; see
`ontology_text_many`/`sparql_query_many`), not only the internal case-transform pipeline.

**`verify.py` deliberately NOT touched this pass** — corrected after closer reading, not
assumed at spec-writing time: its two `templatize_using_name` call sites
(`_expected_artifacts`, `verify_parity`) are the explicit-value *variation*-parity rail (the
P0–P7 crown: substitute a caller-given `variation_value` for the seed and verify the real
`ggen` binary reproduces it byte-exact) — a materially different feature from capture/build
flow, with no defined multi-seed equivalent in this phase's spec above (what would it mean to
substitute new values for *several* seeds at once and verify parity against a real `ggen`
run — genuinely unscoped, not a mechanical extension of the collision-detection work above).
A real gap, named here rather than silently left inconsistent with the rest of this section.

**Deferred within Phase 2** (named, not silently assumed closed): declared constants,
transform ambiguity beyond the cross-seed overlap case above, explicit binary/opaque-copy
policy, the full typed-negative-fixture matrix, and the `MULTI_PARAMETER_PARITY_ALIVE` exit
gate itself (requires all seven `ROADMAP.md` Phase 2 sub-items, not multiple-seeds alone).

### Graph synthesizer

Manufactures:

- exemplar graph;
- parameter and transform graph;
- variation graph;
- projection graph;
- skill graph;
- agent topology graph;
- verifier obligations.

v26.8.6 admits only the subset needed for one lexical seed and deterministic projections. Skills and agent graphs are specified in ontology but not populated.

Canonical ontology namespace: `https://ggen.io/ontology/create#`

### Admission engine

Uses:

- SHACL;
- deterministic query closure;
- path-ownership validation;
- collision checks;
- authority checks;
- unsupported-region accounting;
- verifier completeness.

v26.8.6 admits two checkpoint families:

| Family | Runner | Crown |
| --- | --- | --- |
| repository GALL | `scripts/gall_checkpoint.py` | `ggen-create.gall.crown.v1` |
| hygen parity Gall | `scripts/gall_hygen_parity.py` | `ggen-create.gall.hygen-parity.receipt.v1` |

GALL state law:

```text
CANDIDATE → ADMITTED → ALIVE
```

No checkpoint begins `ALIVE`. `ADMITTED` requires exact revision identity and a clean worktree.

### Package assembler

Emits the inputs consumed by `ggen`, not final target artifacts.

v26.8.6 implementation module: `package.py`

Per admitted source file, emit one `.tmpl` with:

- parameterized `to:` path;
- one SPARQL query selecting all admitted name forms;
- `for_each: entities`;
- Tera body composed from raw static segments and explicit `row.<form>` bindings.

Static source content is wrapped in Tera raw blocks. A source containing the raw-block terminator is refused rather than silently corrupted.

Revision law:

- identical package emission → `changed = false`;
- changed emission archives prior current package as `<generator>.N`.

### Verification coordinator

Creates bounded execution intents to:

- execute the documentation parity rail;
- execute the public ggen rail;
- compare output trees;
- run behavioral commands;
- assemble receipts.

v26.8.6 implementation module: `verify.py`

Documentation rail checkpoints:

| ID | Witness |
| --- | --- |
| G0 | reference identity |
| G1 | reference blobs |
| G2 | capture contract |
| G3 | case corpus |
| G4 | documentation closure |
| G5 | Hello reconstruction |
| G6 | Hola variation and execution |
| G7 | deterministic replay digest |

Product rail checkpoints:

| ID | Witness |
| --- | --- |
| P0 | pinned toolchain identity |
| P1 | bounded capture |
| P2 | lexical transforms |
| P3 | inspection report |
| P4 | exact exemplar reconstruction |
| P5 | changed-parameter variation |
| P6 | revision behavior |
| P7 | byte-exact reference comparison |

`parity-report.json` is the aggregate product receipt.

## Canonical object model

```text
CaptureSession
ExemplarArtifact
ObservedPath
ContentRegion
SymbolOccurrence
ParameterCandidate
Parameter
Transform
VariationAxis
Projection
Skill
AgentRole
VerificationObligation
GeneratorPlan
CheckpointReceipt
AdmissionDecision
```

## Core morphisms

```text
CaptureSession includes ObservedPath
ObservedPath contains SymbolOccurrence
SymbolOccurrence supports ParameterCandidate
Parameter transformedBy Transform
VariationAxis guards Projection
GeneratorPlan contains Projection
Skill consumes admitted input
Skill produces candidate output
AgentRole composes Skill
Artifact verifiedBy VerificationObligation
Receipt proves Checkpoint
```

## Authority model

| Component | Inspect | Select | Construct | Actuate |
| --- | ---: | ---: | ---: | ---: |
| capture engine | yes | bounded | observation graph | no |
| correspondence engine | yes | candidate | correspondence graph | no |
| synthesis agents | yes | bounded | candidate package graph | no |
| Rust `ggen-dspy` | admitted inputs | bounded | typed reasoning/action/code intents | **no** |
| admission referee | yes | admit/refuse | decision object | no |
| documentation parity verifier | yes | no | receipt envelope | bounded (`npm run hola`) |
| BRCE / product verifier | bounded | no | receipt envelope | yes (public `ggen`) |
| host broker | admitted intent | policy | receipt envelope | **exclusive external DO** |
| ggen | admitted inputs | deterministic | artifacts | through receipted runtime |

## v26.8.7 Rust DSPy enterprise boundary

`crates/ggen-dspy` is the admitted Rust reasoning and optimization substrate recovered from the historical `ggen-dspy` lineage. Its target architecture is intentionally not a literal restoration of historical execution semantics.

It admits:

- typed signatures, fields, values, examples and predictions;
- provider-neutral language-model/module contracts;
- Predict and Chain of Thought;
- ReAct that manufactures `ActionIntent` and consumes broker-returned `ToolObservation`;
- retrieval, MultiHopQA and SimplifiedBaleen;
- Program of Thought that manufactures `CodeIntent` and consumes broker-returned `ExecutionResult`;
- labeled/bootstrap few-shot and bounded MIPRO-style optimization;
- evaluation, assertions, explicit config/context/cache/usage;
- completion/chat/JSON/integrated/fallback adapter surfaces;
- reusable agent pattern descriptions.

It refuses ambient authority. The crate does not own process execution, filesystem actuation, network sockets, credentials, generated-code execution, receipts, or standing. `Tool` is metadata, not an executable callback. The host broker remains the exclusive external DO boundary.

Enterprise evidence is split deliberately:

| Artifact | Role |
| --- | --- |
| `architecture/ADR-0001-RUST-DSPY-AUTHORITY.md` | authority decision and supersession law |
| `architecture/ENTERPRISE_ARCHITECTURE.md` | business/application/data/technology/security/operations target architecture |
| `architecture/enterprise.toml` | machine-readable admitted invariants |
| `scripts/enterprise_architecture_check.py` | executable architecture conformance gate |
| `tests/test_enterprise_architecture.py` | positive and falsifier tests |
| `docs/ENTERPRISE_READINESS.md` | integration/environment/release/production gates |

A change to `architecture/enterprise.toml` is both docs-owned and build-owned so architecture authority cannot change without implementation evidence.

## Evidence topology

`ggen-create v26.8.7` uses an 80/20 ERRC CI topology:

```text
exact-head admission
  → path-owned deep lanes
  → GALL crown (always)
  → hygen parity crown (docs/build when present)
```

| Lane | Owned surfaces |
| --- | --- |
| `ci_deep` | `.github/**`, `scripts/ci_*.py`, `scripts/gall_*.py`, `tests/test_ci_*.py`, `docs/ci.md`, `docs/gall.md` |
| `docs_deep` | `README.md`, `BOOTSTRAP.md`, `docs/**`, `architecture/**`, Markdown files |
| `ontology_deep` | `ontology/**` |
| `build_deep` | Cargo/toolchain, `src/**`, `crates/**`, `examples/**`, non-CI tests, unknown future surfaces, `architecture/enterprise.toml` |

Admission receipt schema: `ggen-create.ci.errc.receipt.v2`

Claim ceiling for admission: `EXACT_HEAD_FAST_AUTHORITY_AND_ROUTING_ONLY`

## Skill and agent projection rule

Canonical skill and agent authority remains in RDF.

Consumer-specific files such as:

```text
.claude/skills/<name>/SKILL.md
AGENTS.md
agent manifests
```

are projections. Their loader limitations do not define the canonical ontology.

v26.8.6 does not admit skills or agents.

## Handoff topology

### v26.8.7: minimal agent topology (ADMITTED)

```text
receiver
  ↓ AdmittedRepositoryObservation
correspondence-analyst
  ↓ CandidateCorrespondenceGraph
admission-referee
  ↓ AdmissionDecision
```

Real, implemented types (`src/ggen_create/topology.py`), not ontology placeholders:
`AdmittedRepositoryObservation` wraps a bounded, digest-backed manifest of the subject
repository; `CandidateCorrespondenceGraph` is a byte-exact diff (`equal`/`only_left`/
`only_right`/`different`) between that recorded manifest and a fresh re-walk of the
subject; `AdmissionDecision` carries `standing` (`ADMITTED`/`PARTIAL_ALIVE`/`REFUSED`) and
`reasons`, gated first on zero drift (hard `REFUSED`) then on the manifest's own declared
`blockers`. Implemented as `AdmissionDecision`, superseding this section's original
placeholder name `AdmittedCorrespondenceGraph` for the same handoff — the earlier name was
never admitted/implemented under that identifier. Held-out replay evidence:
`selfplay.py`'s `topology-chain-*` scenarios, run against `ggen-create`'s own repository.

### Post-v26.8.7 agent topology (specified, not admitted)

```text
manufacturing-architect ─────┐
skill-architect              │
topology-architect           │
verification-architect ──────┘
  ↓ CandidateCreatePackage
admission-referee
  ↓ AdmittedCreatePackage
adversarial-verifier
  ↓ ExecutionReceiptSet
certifier
  ↓ ScopedStanding
```

Handoffs are typed graph objects, not an unrestricted chat mesh.

## Separation from ggen-legacy

`ggen-create` is generic.

`ggen-legacy` specializes the create-side architecture for enterprise repository reconstitution:

```text
repository archaeology
contract reconstruction
replacement manufacture
behavioral closure
replay
sunset admission
```

`ggen-legacy` should eventually consume or extend `ggen-create`; it is not merely an archived predecessor.

## Security boundaries

Typed refusals include:

```text
PATH_OUTSIDE_CAPTURE_ROOT_REFUSED
SYMLINK_ESCAPE_REFUSED
OBSERVATION_CHANGED_REFUSED
AMBIGUOUS_TRANSFORM_REFUSED
PARAMETER_COLLISION_REFUSED
OUTPUT_PATH_COLLISION_REFUSED
OUTPUT_ESCAPE_REFUSED
UNBOUND_PARAMETER_REFUSED
NONDETERMINISTIC_PROJECTION_REFUSED
INSUFFICIENT_EXEMPLARS_REFUSED
UNBOUNDED_VARIATION_REFUSED
UNRECEIPTED_ACTUATION_REFUSED
RAW_BLOCK_TERMINATOR_REFUSED
REFUSED:ACTUATION_REQUIRES_BROKER
```

## Determinism

A create package is deterministic only when:

- observations are content-addressed;
- graph ordering is canonical;
- queries have deterministic ordering;
- templates are content-addressed;
- toolchain identities are pinned;
- outputs are compared in empty staging trees;
- replay reproduces the same package and artifact identities.

v26.8.6 proves determinism through:

- G7 tree digest equality for Hola manufacture;
- GALL subprocess replay on every checkpoint;
- package no-op replay on unchanged capture;
- exact-head CI revision binding.

The v26.8.7 Rust DSPy layer additionally requires bounded optimizer search and no ambient clock, randomness, network, filesystem, or process authority for kernel operation, as encoded in `architecture/enterprise.toml`.

## Module map for Phase 1 runtime

| Module | Responsibility |
| --- | --- |
| `session.py` | original-compatible capture lifecycle and bounded path admission |
| `cases.py` | case-family inference, occurrence discovery, Tera parameterization, concrete replay |
| `inspect.py` | mechanical preview and correspondence report |
| `package.py` | deterministic ggen project emission and revision archival |
| `verify.py` | public `ggen` subprocess execution, artifact projection, behavior checks, reference comparison |
| `cli.py` | original-compatible and native command surfaces |

Repository evidence modules already admitted:

| Module | Responsibility |
| --- | --- |
| `scripts/gall_hygen_parity.py` | documentation parity G0–G7 |
| `scripts/gall_checkpoint.py` | repository GALL crown |
| `scripts/ci_admit.py` | exact-head admission and lane execution |
| `scripts/ci_router.py` | deterministic path routing |
| `scripts/enterprise_architecture_check.py` | Rust DSPy enterprise authority conformance |

## Reference binding

Documentation parity is pinned to:

```text
repository: ronp001/hygen-create
commit:     124fac27df0ddbc498b841ba3e05997ed10e4c39
tree:       bf088a9e2ab533cd9ba035ecddb0c31f30e292bd
```

Fixture root: `examples/hygen-create-reference/`

Manifest: `examples/hygen-create-reference/parity.json`

## Initial implementation boundary

The first product runtime slice supports:

- one capture root;
- regular UTF-8 text files;
- one lexical parameter;
- original case-family transforms;
- inspect-before-admit via `status`;
- basic ggen package emission;
- exact reconstruction;
- one changed-value behavioral fixture;
- revision archive on package drift.

No agents are required for this slice.

## Architecture falsifiers

The v26.8.7 architecture is falsified if:

- create-time code directly manufactures target artifacts without an admitted package boundary;
- documentation parity passes while module contracts diverge from this ARD;
- GALL crown claims are inferred from skipped lanes;
- package emission cannot be replayed from content-addressed observations;
- verification requires private `ggen` hooks not available through public CLI boundaries;
- `ggen-dspy` gains ambient process, filesystem, network, FFI, unsafe, or credential authority without an explicit superseding ADR;
- ReAct or Program of Thought directly executes tools/code instead of manufacturing typed intents;
- the reasoning layer can issue its own authoritative execution receipt or standing;
- an architecture-contract change bypasses build evidence.
