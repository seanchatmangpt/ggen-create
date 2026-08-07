# Product Requirements Document

## Product

`ggen-create`

## Version

`v26.8.6`

## Status

Authority admitted. Parity contract executable. Product runtime not yet admitted on `main`.

## Document law

This PRD is the product authority for `ggen-create v26.8.6`. It binds user-visible behavior, release standing, and claim ceilings. Implementation may lag specification only where this document explicitly marks a capability `UNKNOWN` or `OUT_OF_SCOPE`.

Companion authority:

| Document | Role |
| --- | --- |
| `architecture/ARD.md` | system boundary, components, morphisms, security, determinism |
| `docs/hygen-create-parity.md` | pinned hygen-create reference contract |
| `docs/gall.md` | repository promotion checkpoints |
| `docs/ci.md` | evidence topology and replay |
| `ROADMAP.md` | phased delivery after v26.8.6 |

## Problem

A working software artifact already contains valuable manufacturing knowledge, but current generator-authoring workflows require humans or agents to restate that knowledge manually as templates, queries, schemas, skills, and orchestration.

This produces three recurring failures:

1. the generator does not reconstruct the working exemplar;
2. inferred variability is confused with accidental lexical coincidence;
3. successful file emission is treated as proof of a lawful manufacturing system.

At the same time, `ggen` has accumulated pressure to both create manufacturing systems and operate them. These are different products and authority boundaries.

## Product thesis

`ggen-create` converts working exemplars into an admitted, replayable ggen package.

```text
O: working exemplars
→ observation and anti-unification
→ candidate manufacturing graph
→ GALL admission
→ O*: admitted manufacturing graph
→ package for ggen
```

`ggen` then performs construct-time manufacture.

```text
hygen-create: exemplar → Hygen generator → generated project
ggen-create:  exemplar → ggen package    → generated project
```

## v26.8.6 release intent

`v26.8.6` is the first admitted authority release. It does three jobs:

1. **establish product law** — this PRD, the ARD, and a versioned roadmap;
2. **admit the hygen-create parity contract** — byte-exact reference fixture, G0–G7 Gall checkpoints, and documentation closure;
3. **specify the Phase 1 runtime** — the smallest lawful `ggen-create` implementation that can promote `HYGEN_CREATE_PARITY_ALIVE` from documentation-only evidence to executable product evidence.

`v26.8.6` does not claim general repository synthesis, multi-parameter inference, structural anti-unification, skills, agents, MCP, or A2A unless and until a later version admits those checkpoints.

## Users

| Persona | Job |
| --- | --- |
| application developer | turn a repeated implementation into a reusable factory |
| architecture team | reconstruct manufacturing rules from legacy repositories |
| ggen pack author | emit packages consumable by public `ggen` boundaries |
| agent-system builder | manufacture project-specific skills and bounded agent topologies |
| `ggen-legacy` operator | enterprise repository reconstitution as a specialization |

## Primary jobs

### Capture

Pin an exemplar root, explicitly include files, classify unsupported content, and produce an immutable observation identity.

v26.8.6 requires:

- one capture root per session;
- explicit file admission only;
- UTF-8 regular files for the parity rail;
- refusal of paths outside root, symlinks, binary payloads, and NUL bytes;
- a session manifest compatible with the original six-field `hygen-create.json` shape.

### Infer

Derive candidate parameters, lexical transforms, structural correspondences, optional regions, repeated regions, and bounded variation axes.

v26.8.6 requires:

- one lexical seed parameter;
- the original hygen-create case family:
  - `upper`, `lower`, `capitalized`, `pascal`, `camel`, `snake`, `upper_snake`, `kebab`;
- left-boundary replacement law identical to the pinned reference corpus;
- duplicate lexical forms resolved by the original priority order.

v26.8.6 excludes:

- multiple simultaneous seeds;
- Tree-sitter structural anti-unification;
- variation-axis inference from a single exemplar.

### Inspect

Expose every proposed correspondence, collision, ambiguity, unsupported region, and target projection before admission.

v26.8.6 requires `status` to report, mechanically and without side effects:

- admitted source path;
- parameterized target path;
- path and content occurrences;
- transform selected for each occurrence;
- total replacement count;
- parent-directory mode.

### Admit

Validate the candidate graph through SHACL, deterministic closure, authority checks, path ownership, and verifier obligations.

v26.8.6 admits:

- repository GALL crown checkpoints (`exact_head` through `receipt`);
- hygen parity Gall checkpoints (`G0` through `G7`);
- Phase 1 package receipts only after positive execution evidence exists.

v26.8.6 does not admit:

- skills or agents;
- Markdown projections as canonical skill authority;
- parity from source inspection alone.

### Package

Emit the inputs consumed by `ggen`, not final target artifacts.

v26.8.6 requires package emission to produce, at minimum:

```text
<package-root>/<generator>/
├── ggen.toml
├── ontology.ttl
├── templates/*.tmpl
├── ggen-create-package.json
└── receipt.json
```

Package law:

- identical rerun yields `changed = false`;
- changed package archives prior current package as `<generator>.1`, `<generator>.2`, ...;
- identical source tree digest must produce identical package tree digest.

### Verify

Reconstruct original exemplars, exercise changed parameters, execute behavioral obligations, and issue receipts.

v26.8.6 requires two verification rails:

| Rail | Purpose | Crown |
| --- | --- | --- |
| documentation parity | bind examples and prose to pinned upstream bytes | `EXAMPLE_DOCUMENTATION_AND_LOCAL_REFERENCE_CONSEQUENCE_ONLY` |
| product parity | prove the admitted CLI and public `ggen` reproduce hygen-create consequences | `HYGEN_CREATE_PARITY_ALIVE` |

The documentation rail is **ALIVE** in v26.8.6 through `scripts/gall_hygen_parity.py`.

The product rail remains **UNKNOWN** on `main` until Phase 1 runtime checkpoints pass under exact-head CI.

## User-visible CLI

### Product split

```text
ggen-create  creates admitted factories
ggen         operates admitted factories
```

No `ggen-create construct-target` command is permitted. Verification may invoke public `ggen` in isolated staging; that is verification of a manufactured factory, not an embedded construction engine.

### v26.8.6 command surface

Original-compatible commands:

```bash
ggen-create start <generator-name> [--root <path>]
ggen-create rename <generator-name>
ggen-create add [-r] <file-or-dir>...
ggen-create remove <file>...
ggen-create rm <file>...
ggen-create usename <seed>
ggen-create setopt --gen-parent-dir
ggen-create setopt --no-parent-dir
ggen-create status [-v] [file...]
ggen-create s [-v] [file...]
ggen-create generate [--output <dir>] [--force]
ggen-create g [--output <dir>] [--force]
ggen-create abort
ggen-create verify <options>
ggen-create compare <left-tree> <right-tree>
```

Native aliases for the same deterministic skills:

```bash
ggen-create capture init <name> [--root <path>]
ggen-create capture include [-r] <path>...
ggen-create capture remove <path>...
ggen-create capture abort
ggen-create parameter seed <value>
ggen-create package build [--output <dir>] [--force]
ggen-create parity verify <options>
ggen-create parity compare <left-tree> <right-tree>
```

Global options:

```bash
-p, --project <capture-file>   # default: ggen-create.json
--json                         # machine-readable output
```

Reserved commands must not ship as stubs. Unsupported future capability remains absent from the executable surface until its checkpoint exists.

### Canonical parity journey

```bash
ggen-create start greeter
ggen-create add package.json dist/hello.js
ggen-create usename Hello
ggen-create status
ggen-create generate
```

Changed-value manufacture:

```bash
mkdir -p /tmp/hola-greeter && cd /tmp/hola-greeter
ggen greeter new --name Hola
npm run hola
```

Required consequence:

```text
dist/hola.js exists
package.json scripts.hola = "node dist/hola.js"
stdout = Hola!
```

## Explicit non-goals for v26.8.6

- operating target factories directly;
- replacing `ggen sync`;
- unrestricted LLM template generation;
- inventing variation axes from one exemplar without evidence;
- allowing skills or agents to execute shell commands directly;
- treating Markdown skill projections as canonical skill authority;
- claiming parity from source inspection alone;
- claiming generalization from reconstruction alone;
- MCP, A2A, automatic, or autonomic controllers;
- enterprise `ggen-legacy` repository archaeology.

## Success criteria

### Documentation parity — ALIVE in v26.8.6

`EXAMPLE_DOCUMENTATION_AND_LOCAL_REFERENCE_CONSEQUENCE_ONLY` requires:

| Checkpoint | Consequence |
| --- | --- |
| G0 | pinned reference repository, commit, tree |
| G1 | four byte-exact upstream example files |
| G2 | ordered capture fields, generator, seed, file set, parent policy |
| G3 | all 24 case-family comparisons |
| G4 | README and parity guide bind commands, paths, output, revision facts |
| G5 | `Hello` reconstructs captured files byte-exactly |
| G6 | `Hola` creates `dist/hola.js` and `npm run hola` prints `Hola!` |
| G7 | two independent manufactures share tree digest |

### Product parity — required for v26.8.6 GA

`HYGEN_CREATE_PARITY_ALIVE` additionally requires:

- real `ggen-create` CLI implementing the v26.8.6 command surface;
- real public `ggen` reconstructs `Hello` byte-exactly;
- real public `ggen` generates `Hola` with equivalent tree and behavior;
- original `hygen-create` independently generates `Hola` for cross-rail comparison;
- revision archive law (`greeter.1`) on changed package emission;
- machine-readable `parity-report.json` with P0–P7 standing;
- exact-head workflow publishes parity evidence.

P7 may be `ALIVE` only when both `--reference-dir` and `--reference-id` are supplied and byte-exact comparison succeeds.

### ggen-native success — post v26.8.6

`GGEN_CREATE_PACKAGE_ALIVE` is out of scope for v26.8.6. It additionally requires:

- canonical RDF manufacturing graph;
- SHACL-conformant package;
- admitted skills and justified bounded agents;
- held-out self-play;
- scoped claim ceiling beyond hygen parity.

## Performance objectives

Greeter parity fixture:

| Objective | Target |
| --- | --- |
| inspection | < 1 s for the admitted three-file exemplar |
| reconstruct-and-vary | < 5 s excluding first-time toolchain acquisition |
| deterministic replay | identical second run |
| network | no hidden network requirement after dependencies are cached |

## Standing model

```text
UNKNOWN          capability not yet evidenced
PARTIAL_ALIVE    some checkpoints pass; crown claim forbidden
ALIVE            all admitted checkpoints pass under replay
REFUSED:*        typed admission refusal
BUILD_BROKEN:*   implementation or evidence failure
UNSUPPORTED:*    environment lacks required witness
```

v26.8.6 admitted standing on `main`:

```text
reference identity and fixture bytes:     ALIVE
case-family unit contract:                ALIVE
example reconstruction and variation:     ALIVE
documentation-to-example closure:         ALIVE
ggen-create CLI and package runtime:        ALIVE (local unit evidence)
real public ggen parity crown (P7):         UNKNOWN until exact-head CI with ggen
```

## Product falsifiers

The design is falsified if any of these become necessary:

- `ggen-create` must bypass public ggen APIs to prove its package;
- agents require direct filesystem or process authority in v26.8.6;
- parity cannot be demonstrated without semantic weakening;
- package identity cannot bind all source observations and generated projections;
- held-out behavior cannot distinguish inference from memorization;
- documentation checkpoints pass while the CLI diverges from admitted commands.

## Release gates

`v26.8.6` authority may merge when:

1. this PRD and `architecture/ARD.md` are admitted;
2. hygen parity G0–G7 are `ALIVE` under `docs_deep` and `build_deep`;
3. GALL crown is `ALIVE` on exact-head CI;
4. README links product and architecture authority.

`v26.8.6` GA may be claimed only when `HYGEN_CREATE_PARITY_ALIVE` is `ALIVE` under exact-head CI with public `ggen` execution evidence.
