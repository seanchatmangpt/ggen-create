# AGENTS.md

## Mission

Build `ggen-create` as the create-side companion to `ggen`.

```text
ggen-create: exemplars → admitted manufacturing system
ggen:        admitted manufacturing system + subject → artifacts + receipts
```

Do not collapse these categories.

## Foundational order

1. Preserve the working exemplar.
2. Fence the observation boundary.
3. Define objects, morphisms, admission, closure, authority, actuation, receipt, and replay.
4. State exclusions.
5. State falsifiers.
6. Extend only after a smaller rail is ALIVE.
7. Operationalize with exact commands and receipts.

## Standing vocabulary

Use only:

```text
UNKNOWN
PARTIAL_ALIVE
ALIVE
BLOCKED
BUILD_BROKEN
UNSUPPORTED
REFUSED(<typed reason>)
```

Track separately:

- observed
- admitted
- executed
- changed
- verified
- inferred
- refused
- blocked
- unsupported

Inspection is not execution. A generated skill file is not an admitted skill. An agent description is not an executed agent topology.

## Authority

### SELECT

May choose among admitted reversible candidates.

### CONSTRUCT

May manufacture candidate graphs, package files, verifier definitions, skills, agent roles, and intents.

### DO

May change filesystem state or execute processes only through BRCE. Zero unreceipted actuation.

Skills and agents have no ambient DO authority.

## Repository ownership

Canonical hand-edited surfaces:

```text
product/
architecture/
docs/
ontology/
shapes/
schemas/
examples/
```

Future generated projections must be clearly marked and must not be edited by hand.

## Two ladders

### Parity ladder

No agents in the first ALIVE implementation. Use fixed deterministic skills and real subprocess execution of the exact `ggen` and reference Hygen toolchains.

### ggen-native ladder

Agents may be introduced only after parity standing is ALIVE. Agent boundaries require distinct authority, input domain, verifier, failure boundary, file ownership, or replayable handoff.

## Implementation discipline

- Resolve the exact base SHA before work.
- Read root and nested doctrine before editing.
- Prefer the smallest coherent diff.
- Do not hand-edit generated outputs.
- Do not fabricate execution evidence.
- Do not weaken tests to obtain green status.
- Do not replace requested CLI, integration, protocol, or behavioral proof with unit-only proof.
- On failure, classify the failed transition before repair.
- Never rerun an unchanged failure without a new hypothesis.
- Default to a draft PR.
- Never merge unless explicitly requested.

## Acceptance order

1. narrow verifier
2. unit
3. integration
4. end-to-end
5. held-out self-play
6. replay
7. exact-head CI as supplementary evidence

Local execution remains required unless explicitly reclassified.

## Initial file-count boundary

Prefer changes within 12 files unless dependency closure requires more.
