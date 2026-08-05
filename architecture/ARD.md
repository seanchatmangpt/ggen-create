# Architecture Requirements and Design

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

## Context

```text
┌───────────────────┐
│ Working exemplars │
└─────────┬─────────┘
          │ observe
┌─────────▼─────────┐
│    ggen-create    │
│ SELECT/CONSTRUCT  │
└─────────┬─────────┘
          │ admitted package
┌─────────▼─────────┐
│       ggen        │
│ deterministic DO │
└─────────┬─────────┘
          │ artifacts + receipts
┌─────────▼─────────┐
│ verifier / mfact  │
└───────────────────┘
```

## Major components

### Capture engine

Responsibilities:

- root fencing;
- explicit include/exclude;
- file and tree hashing;
- symlink and binary classification;
- parser outcome recording;
- immutable subject identity.

### Correspondence engine

Tiers:

1. deterministic lexical anti-unification;
2. Tree-sitter structural anti-unification;
3. multi-exemplar variation-axis inference.

All output is candidate evidence until admitted.

### Graph synthesizer

Manufactures:

- exemplar graph;
- parameter and transform graph;
- variation graph;
- projection graph;
- skill graph;
- agent topology graph;
- verifier obligations.

### Admission engine

Uses:

- SHACL;
- deterministic query closure;
- path-ownership validation;
- collision checks;
- authority checks;
- unsupported-region accounting;
- verifier completeness.

### Package assembler

Emits the inputs consumed by `ggen`, not final target artifacts.

### Verification coordinator

Creates BRCE intents to:

- execute the reference Hygen rail;
- execute the public ggen rail;
- compare output trees;
- run behavioral commands;
- run held-out self-play;
- assemble receipts.

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
|---|---:|---:|---:|---:|
| capture engine | yes | bounded | observation graph | no |
| correspondence skills | yes | candidate | correspondence graph | no |
| synthesis agents | yes | bounded | candidate package graph | no |
| admission referee | yes | admit/refuse | decision object | no |
| BRCE | bounded | no | receipt envelope | yes |
| ggen | admitted inputs | deterministic | artifacts | through its receipted runtime |

## Skill/agent projection rule

Canonical skill and agent authority remains in RDF.

Consumer-specific files such as:

```text
.claude/skills/<name>/SKILL.md
AGENTS.md
agent manifests
```

are projections. Their loader limitations do not define the canonical ontology.

## Handoff topology

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

## Initial implementation boundary

The first implementation supports:

- one capture root;
- regular text files;
- one lexical parameter;
- original case-family transforms;
- preview;
- basic ggen package emission;
- exact reconstruction;
- one changed-value behavioral fixture.

No agents are required for this slice.
