# ggen-create

**Exemplar-to-ggen reverse compiler with Gall's-Law checkpoints.**

`ggen-create` observes working exemplars, manufactures a candidate ggen manufacturing system, admits that system through explicit checkpoints, and emits a package that the separate `ggen` CLI can execute.

> Create the factory. Admit the factory. Let ggen operate the factory.

## Architectural fence

```text
working exemplars
      ↓
ggen-create
      ↓
admitted ggen package
      ↓
ggen sync
      ↓
artifacts + receipts
```

`ggen-create` is create-time. `ggen` is construct-time.

`ggen-create` must not become a second template engine, and `ggen` must not absorb repository archaeology, exemplar anti-unification, skill synthesis, or agent-topology inference.

## Influences

The immediate architectural influence is [`ronp001/hygen-create`](https://github.com/ronp001/hygen-create):

```text
existing working files
→ select files
→ seed a name
→ infer lexical transformations
→ preview
→ emit a reusable generator
```

`ggen-create` preserves that exemplar-first flow, but replaces ad hoc template authority with an admitted graph, SHACL constraints, held-out verification, and replayable receipts.

[`seanchatmangpt/ggen-legacy`](https://github.com/seanchatmangpt/ggen-legacy) is the large enterprise specialization of this problem: repository archaeology, contract reconstruction, replacement manufacture, behavioral closure, replay, and predecessor-retirement standing.

## Two checkpoint ladders

### 1. Parity ladder

Proves that `ggen-create` can perform the original `hygen-create` job:

1. reference identity
2. capture parity
3. lexical transformation parity
4. inspection parity
5. exact reconstruction
6. changed-parameter variation
7. iterative revision
8. parity receipt

This rail is deterministic and initially uses **no agents**.

### 2. ggen-native ladder

Begins only after parity is ALIVE:

1. canonical graph creation
2. SHACL and authority admission
3. native ggen package manufacture
4. skill synthesis
5. bounded subagent synthesis
6. held-out self-play
7. self-hosting and replay

## Core invariants

- `A = μ(O*)`: only admitted observations may manufacture artifacts with standing.
- Zero unreceipted actuation.
- Skills construct candidate objects; they do not receive ambient execution authority.
- Agents compose skills and manufacture intents; BRCE is the exclusive DO path.
- `UNKNOWN` is not admitted.
- `UNSUPPORTED` is not `REFUSED`.
- A successful render is not behavioral proof.
- A checkpoint is not the crown.
- Generated projections are not canonical editing surfaces.

## Initial repository standing

```text
architecture:                 ADMITTED
parity checkpoint design:     ADMITTED
ggen-native checkpoint design: ADMITTED
skills and agents design:     ADMITTED
runtime implementation:       UNKNOWN
parity execution:             NOT EXECUTED
ggen-native self-play:         NOT EXECUTED
```

## Canonical authority

1. [`AGENTS.md`](AGENTS.md)
2. [`product/PRD.md`](product/PRD.md)
3. [`architecture/ARD.md`](architecture/ARD.md)
4. [`docs/CHECKPOINTS.md`](docs/CHECKPOINTS.md)
5. [`docs/SKILLS_AND_AGENTS.md`](docs/SKILLS_AND_AGENTS.md)
6. [`docs/CLI_CONTRACT.md`](docs/CLI_CONTRACT.md)
7. [`ontology/ggen-create.ttl`](ontology/ggen-create.ttl)
8. [`shapes/ggen-create.shacl.ttl`](shapes/ggen-create.shacl.ttl)
9. [`ROADMAP.md`](ROADMAP.md)

## First ALIVE slice

The first implementation must remain intentionally small:

```text
capture-session
capture-paths
seed-parameter
lexical-anti-unify
preview-correspondence
emit-basic-ggen-package
reconstruct-exemplar
verify-parity-variation
```

Canonical fixture:

```text
Hello project
→ inferred greeter package
→ reconstruct Hello
→ generate Hola
→ execute Hola
→ parity receipt
```
