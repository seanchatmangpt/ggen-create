# Architecture Requirements and Design

## Product

`ggen-create`

## Version

`v26.8.6`

## Status

Architecture authority admitted. Documentation parity rail implemented. Product runtime (CLI and package build) admitted on `main` with local unit evidence; the external P7 crown against a real `ggen` binary and upstream `hygen-create` remains `UNKNOWN`.

## Document law

This ARD is the architecture authority for `ggen-create v26.8.6`. It binds system boundaries, component responsibilities, object model, security refusals, and determinism law. Product behavior is normative in `product/PRD.md`; this document explains how that behavior is manufactured and verified.

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
| multi-parameter collision law | Phase 2 |
| multi-exemplar variation axes | Phase 4 |
| skills and agents | Phase 5+ |
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
| admission referee | yes | admit/refuse | decision object | no |
| documentation parity verifier | yes | no | receipt envelope | bounded (`npm run hola`) |
| BRCE / product verifier | bounded | no | receipt envelope | yes (public `ggen`) |
| ggen | admitted inputs | deterministic | artifacts | through receipted runtime |

## Evidence topology

`ggen-create v26.8.6` uses an 80/20 ERRC CI topology:

```text
exact-head admission
  → path-owned deep lanes
  → GALL crown (always)
  → hygen parity crown (docs/build when present)
```

| Lane | Owned surfaces |
| --- | --- |
| `ci_deep` | `.github/**`, `scripts/ci_*.py`, `scripts/gall_*.py`, `tests/test_ci_*.py`, `docs/ci.md`, `docs/gall.md` |
| `docs_deep` | `README.md`, `BOOTSTRAP.md`, `docs/**`, Markdown files |
| `ontology_deep` | `ontology/**` |
| `build_deep` | Cargo/toolchain, `src/**`, `examples/**`, non-CI tests, unknown future surfaces |

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

Post-v26.8.6 agent topology (specified, not admitted):

```text
receiver
  ↓ AdmittedRepositoryObservation
correspondence-analyst
  ↓ CandidateCorrespondenceGraph
admission-referee
  ↓ AdmittedCorrespondenceGraph
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

The v26.8.6 architecture is falsified if:

- create-time code directly manufactures target artifacts without an admitted package boundary;
- documentation parity passes while module contracts diverge from this ARD;
- GALL crown claims are inferred from skipped lanes;
- package emission cannot be replayed from content-addressed observations;
- verification requires private `ggen` hooks not available through public CLI boundaries.
