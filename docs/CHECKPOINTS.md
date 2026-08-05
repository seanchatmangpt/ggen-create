# Checkpoint Ladders

`ggen-create` has two independent checkpoint sets.

A later ggen-native checkpoint cannot retroactively substitute for missing parity evidence.

# A. Original-parity ladder

## P0 — Reference identity

Bind:

- exact `ronp001/hygen-create` commit;
- exact Hygen commit/version;
- Node/npm toolchain;
- reference fixture corpus;
- commands and environment.

Standing:

```text
ORIGINAL_REFERENCE_ADMITTED
```

## P1 — Capture parity

Prove equivalent ability to:

- initialize a capture;
- include files explicitly;
- fence the capture root;
- refuse missing/out-of-root paths;
- preserve session state;
- record a parameter seed.

## P2 — Transformation parity

For the parity corpus, prove recognition of:

```text
UPPERCASE
lowercase
Capitalized
CamelCase
lowerCamelCase
underscore_case
UPPER_UNDERSCORE_CASE
dash-case
Title Case
```

Path and content transforms must agree.

## P3 — Inspection parity

Expose at least:

- included paths;
- source occurrence;
- proposed parameter;
- proposed transform;
- before/after text;
- target path;
- collision;
- ambiguity;
- unsupported content.

Formatting need not match the original; observable information must be equivalent or stronger.

## P4 — Exact reconstruction

Run:

```text
ggen-create package
→ public ggen execution
→ empty staging tree
```

with the original parameter assignment.

Compare complete artifact trees.

Pass state:

```text
RECONSTRUCTION_ALIVE
```

This is not yet generalization.

## P5 — Variation parity

Run a non-original assignment through both rails:

```text
hygen-create → Hygen
ggen-create  → ggen
```

Canonical fixture:

```text
Hello → Hola
```

Compare paths, content, and behavior.

## P6 — Iterative revision parity

Prove:

```text
exemplar
→ generator v1
→ generated exemplar
→ modification
→ generator v2
→ revised output
```

Generator revisions must have immutable identity and no silent overwrite.

## P7 — Parity crown

Receipt binds:

- all exact subjects;
- reference and ggen-create package identities;
- commands and exits;
- tree manifests;
- equivalence policy;
- behavioral assertions;
- intentional divergences;
- replay result.

Crown:

```text
HYGEN_CREATE_PARITY_ALIVE
```

# B. ggen-native ladder

Begins only after P7.

## G0 — Canonical graph creation

The manufacturing system exists as RDF authority rather than only templates and configuration.

## G1 — SHACL and authority admission

Prove:

- complete parameter domains;
- unique output ownership;
- bounded paths;
- declared transforms;
- deterministic queries;
- explicit unsupported regions;
- no ambient actuation authority.

## G2 — Native ggen package

Manufacture and execute through public ggen boundaries:

```text
ontology
queries
templates
manifest
shapes
fixtures
verification obligations
```

## G3 — Skill admission

A skill is admitted only when it binds:

```text
identity
trigger
inputs
outputs
authority
evidence
verifier
refusals
replay
```

A `SKILL.md` file alone has no crown.

## G4 — Agent admission

An agent boundary requires evidence of distinct:

- authority;
- input domain;
- verifier;
- failure boundary;
- file ownership;
- replayable handoff.

Agents manufacture candidate objects and intents only.

## G5 — Held-out self-play

Challenge the package with unseen subjects and negative fixtures.

Required classes include:

- unseen names;
- casing collisions;
- optional branches;
- empty collections;
- conflicting outputs;
- unsupported languages;
- malformed ontology;
- dishonest triggers;
- unauthorized handoffs.

## G6 — Self-hosting

```text
ggen-create source
→ inferred ggen-create package
→ admitted package
→ ggen constructs ggen-create
→ validation
→ replay match
```

## G7 — Native crown

Receipt DAG binds source, graph, package, skills, agents, held-out runs, and replay.

Crown:

```text
GGEN_CREATE_PACKAGE_ALIVE
```

# Checkpoint state rules

- inspection does not satisfy execution;
- package construction does not satisfy target behavior;
- reconstruction does not satisfy generalization;
- one successful agent route does not admit the topology;
- CI metadata without exact-head logs is not execution evidence;
- unsupported content must remain visible;
- typed refusal is a valid result and must not be collapsed into failure or truth.
