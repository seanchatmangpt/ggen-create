# Skills and Agents

## Definitions

### Skill

A bounded reusable create-time transformation.

A skill consumes an admitted input object and produces a candidate output object. It has no ambient actuation authority.

### Agent

A bounded role that selects and composes admitted skills, owns a specific candidate graph region, and hands off typed objects.

### Referee

An independent admission role. It does not repair the candidate it judges.

## Parity skills

The first parity implementation is deterministic and agent-free.

| Skill | Input | Output |
|---|---|---|
| `capture-session` | root + policy | capture identity |
| `capture-paths` | capture + paths | observed path graph |
| `seed-parameter` | exemplar token | parameter candidate |
| `lexical-anti-unify` | observations + seed | candidate correspondences |
| `preview-correspondence` | candidate graph | inspection report |
| `emit-basic-ggen-package` | admitted correspondence graph | basic ggen package |
| `reconstruct-exemplar` | package + original assignment | reconstruction receipt |
| `verify-parity-variation` | package + changed assignment | parity receipt |
| `link-generator-revision` | old/new package identities | revision edge |

## ggen-native skills

| Skill | Purpose |
|---|---|
| `repository-receive` | inventory repository identity, languages, manifests, entrypoints, tests, authority |
| `exemplar-cluster` | distinguish related exemplars from adjacent artifacts |
| `structural-anti-unify` | derive syntax-tree correspondences |
| `variation-axis-infer` | derive bounded dimensions from multiple exemplars |
| `ontology-synthesize` | manufacture canonical manufacturing ontology |
| `query-synthesize` | manufacture deterministic SPARQL CONSTRUCT/SELECT |
| `template-synthesize` | manufacture projection templates |
| `shape-synthesize` | manufacture SHACL gates |
| `verification-obligation-synthesize` | derive required verifier ladder |
| `skill-synthesize` | manufacture canonical skills and consumer projections |
| `agent-topology-synthesize` | manufacture justified bounded role graph |
| `package-assemble` | assemble complete ggen package |
| `held-out-self-play` | challenge package with unseen subjects |
| `receipt-dag-assemble` | bind create-time evidence and standing |

## Canonical skill contract

Required fields:

```text
identity
version
trigger
accepted input class
produced output class
authority
evidence requirement
verifier
typed refusals
replay inputs
standing
```

Example:

```turtle
gcreate:StructuralAntiUnifySkill
    a gcreate:Skill ;
    gcreate:authority gcreate:ConstructOnly ;
    gcreate:accepts gcreate:AdmittedExemplarGraph ;
    gcreate:produces gcreate:CandidateCorrespondenceGraph ;
    gcreate:verifiedBy gcreate:HeldOutStructuralReplay ;
    gcreate:mayActuate false .
```

## Canonical agent contract

Required fields:

```text
role
allowed skills
accepted input graph
produced output graph
owned graph region
prohibited actions
handoff targets
stop conditions
typed refusals
verifier
```

## Agent topology

### `receiver`

Admits exact repository identity and observation boundary.

Skills:

- `repository-receive`
- `capture-session`
- `capture-paths`

Cannot infer templates or execute build commands directly.

### `correspondence-analyst`

Discovers candidate invariants and variation.

Skills:

- `exemplar-cluster`
- `lexical-anti-unify`
- `structural-anti-unify`
- `variation-axis-infer`

Produces `CandidateCorrespondenceGraph`.

### `manufacturing-architect`

Translates admitted correspondences into ontology, queries, templates, and shapes.

Produces `CandidateManufacturingGraph`.

### `verification-architect`

Independently derives fixtures and verification obligations.

Producer and verifier design remain separated.

### `skill-architect`

Manufactures canonical project capabilities and consumer-specific skill projections.

### `topology-architect`

Creates multiple agents only where independently justified.

It must prefer one capable role over decorative decomposition.

### `admission-referee`

Checks:

- evidence closure;
- SHACL conformance;
- path ownership;
- authority;
- deterministic ordering;
- unsupported claims;
- handoff cycles;
- verifier independence.

Produces only:

```text
ADMITTED
REFUSED(<typed reason>)
UNSUPPORTED
```

### `adversarial-verifier`

Executes held-out self-play through BRCE and public tool boundaries.

### `certifier`

Assembles the receipt DAG and computes the narrowest defensible standing.

## Handoff graph

```text
receiver
  ↓ AdmittedRepositoryObservation
correspondence-analyst
  ↓ CandidateCorrespondenceGraph
admission-referee
  ↓ AdmittedCorrespondenceGraph
manufacturing-architect ────┐
skill-architect             │
topology-architect          │
verification-architect ─────┘
  ↓ CandidateCreatePackage
admission-referee
  ↓ AdmittedCreatePackage
adversarial-verifier
  ↓ ExecutionReceiptSet
certifier
  ↓ ScopedStanding
```

## Projection rule

Canonical skill and agent data remains in RDF.

Files such as `.claude/skills/<name>/SKILL.md` are generated projections constrained by the target loader. Loader limitations do not erase canonical authority fields.

## Introduction sequence

1. deterministic parity skills, no agents;
2. receiver + correspondence analyst + referee;
3. manufacturing architect + verification architect;
4. skill architect + topology architect;
5. adversarial verifier + certifier;
6. self-hosted topology.

This order is mandatory unless a smaller executed rail proves an alternative evolution.
