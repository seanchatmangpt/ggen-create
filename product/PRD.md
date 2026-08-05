# Product Requirements Document

## Product

`ggen-create`

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

## Users

- developers converting repeated implementations into reusable factories;
- architecture teams reconstructing manufacturing rules from legacy repositories;
- ggen pack authors;
- agent-system builders manufacturing project-specific skills and subagent topologies;
- `ggen-legacy` as the enterprise repository-reconstitution specialization.

## Primary jobs

### Capture

Pin an exemplar root, explicitly include files, classify unsupported content, and produce an immutable observation identity.

### Infer

Derive candidate parameters, lexical transforms, structural correspondences, optional regions, repeated regions, and bounded variation axes.

### Inspect

Expose every proposed correspondence, collision, ambiguity, unsupported region, and target projection before admission.

### Admit

Validate the candidate graph through SHACL, deterministic closure, authority checks, path ownership, and verifier obligations.

### Package

Emit a complete ggen manufacturing package:

```text
ontology/
queries/
templates/
shapes/
fixtures/
verification/
skills/
agents/
ggen.toml
```

### Verify

Reconstruct original exemplars, exercise changed parameters, run held-out subjects, execute behavioral obligations through BRCE, and issue receipts.

## Explicit non-goals

- operating target factories directly;
- replacing `ggen sync`;
- unrestricted LLM template generation;
- inventing variation axes from one exemplar without evidence;
- allowing skills or agents to execute shell commands directly;
- treating Markdown skill projections as canonical skill authority;
- claiming parity from source inspection alone;
- claiming generalization from reconstruction alone.

## Success criteria

### Parity success

`HYGEN_CREATE_PARITY_ALIVE` requires:

- pinned reference identity;
- equivalent bounded capture;
- equivalent lexical case-family transforms;
- equivalent inspection information;
- exact exemplar reconstruction;
- changed-name output and behavior;
- iterative revision identity;
- machine-readable parity receipt.

### ggen-native success

`GGEN_CREATE_PACKAGE_ALIVE` additionally requires:

- canonical RDF manufacturing graph;
- SHACL-conformant package;
- executable through public `ggen` boundaries;
- admitted skills;
- justified bounded agents;
- held-out self-play;
- deterministic replay;
- scoped claim ceiling.

## User-visible CLI principles

- create-time verbs live in `ggen-create`;
- construct-time verbs remain in `ggen`;
- inspect before admit;
- admit before package;
- package before target manufacture;
- verification reports exact subjects, commands, exits, and receipts.

## Performance objectives

Initial parity fixture:

- inspection under 1 second for a small project;
- full reconstruct-and-vary checkpoint under 5 seconds excluding first-time toolchain acquisition;
- deterministic second replay;
- no hidden network requirement after dependencies are cached.

## Product falsifiers

The design is falsified if any of these become necessary:

- `ggen-create` must bypass public ggen APIs to prove its package;
- agents require direct filesystem or process authority;
- parity cannot be demonstrated without semantic weakening;
- package identity cannot bind all source observations and generated projections;
- held-out behavior cannot distinguish inference from memorization.
