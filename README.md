# ggen-create

**Automatic and autonomic exemplar-to-ggen factory compiler with MCP and A2A.**

`ggen-create` observes working exemplars, manufactures a reusable ggen factory, and verifies that the separate `ggen` CLI reconstructs and varies those exemplars correctly.

> Create the factory. Admit the factory. Let ggen operate the factory.

## Architectural fence

```text
working exemplars
      ↓
ggen-create
      ↓
admitted ggen package
      ↓
ggen sync run
      ↓
artifacts + receipts
```

`ggen-create` is create-time. `ggen` is construct-time. Skills and agents manufacture candidate graphs and intents; the Broker is the exclusive confirmed native DO boundary.

## Install

```bash
python -m pip install -e .
ggen-create --help
ggen-create-mcp --help
ggen-create-a2a --help
```

The runtime is dependency-free on Python 3.11+.

## Original-compatible parity

```bash
ggen-create start greeter
ggen-create add package.json dist/hello.js
ggen-create usename Hello
ggen-create status --verbose
ggen-create generate --output ../packages
```

Implemented original-compatible commands:

```text
start rename add remove/rm usename setopt
status/s generate/g abort verify compare
```

The parity rail executes P0–P7: reference identity, bounded capture, lexical transformations, inspection, exact reconstruction, changed-parameter variation, revision behavior, and original-reference comparison. Ordinary artifacts are byte-exact. The original `hygen-create.json` and current `ggen-create.json` control manifests are compared through one explicit semantic normalization policy covering only the root filename alias, its self-entry, and capture-tool version identity.

## Automatic mode

```bash
ggen-create automatic plan --output _ggen
ggen-create automatic run --output _ggen --confirm
ggen-create automatic watch --output _ggen --cycles 3 --confirm
```

Planning is reversible and writes nothing. Apply requires explicit confirmation, records the exemplar fingerprint, verifies the emitted package against its package receipt, and emits a chained native receipt. Watch persists its prior fingerprint, performs a real stable no-op, and repairs either exemplar drift or package-integrity drift.

## Autonomic mode

```bash
ggen-create autonomic run \
  --output _ggen \
  --max-cycles 4 \
  --stable-cycles 2 \
  --apply \
  --confirm
```

The controller is a bounded integrity-aware MAPE-K loop. It distinguishes absent, corrupted, knowledge-drifted, and exemplar-drifted factories. It stops on convergence, a typed block, or the configured cycle ceiling. An unconverged ceiling is `PARTIAL_ALIVE`, never `ALIVE`.

## Package and ledger verification

```bash
ggen-create package verify --output _ggen
ggen-create receipt latest
ggen-create receipt verify
ggen-create receipt chain
ggen-create --json doctor
```

Package verification compares every emitted byte with `receipt.json`. Native receipt-chain verification rejects duplicate digests, multiple roots, branches, cycles or incomplete traversal, orphan parents, subject-root drift, tampering, and stale `latest.json` pointers.

## Skills and agents

```bash
ggen-create skills list
ggen-create agents list
ggen-create agents route "manufacture package"
ggen-create selfplay run --confirm
```

Sixteen canonical skills and nine bounded agents are implemented. Every skill and agent declares `mayActuate=false`. Each skill also declares whether it requires a capture session. Root-global inspection, routing, doctor, and ledger operations work without a capture; capture-bound operations refuse with typed session errors. Native write skills require explicit confirmation and cross the Broker boundary. Confirmed failures receive typed failure receipts as well as successful consequences.

## MCP

```bash
ggen-create-mcp --root .
# or
ggen-create mcp serve --root .
```

Profile:

- protocol revision `2025-11-25`;
- stdio JSON-RPC transport;
- strict initialize → initialized lifecycle;
- 14 tools and six allowlisted resources;
- prompts and durable task get/list/result/cancel methods;
- negotiated task-augmented execution with TTL and polling metadata;
- related-task metadata on terminal results;
- schema validation and explicit confirmation on every write tool;
- package-integrity, automatic-watch, autonomic-cycle, receipt-chain, and doctor projections;
- session-independent doctor, routing, and ledger tools on empty subject roots.

See [`docs/MCP.md`](docs/MCP.md).

## A2A

```bash
ggen-create a2a card
ggen-create-a2a --root . --host 127.0.0.1 --port 8765
```

Profile:

- protocol profile `1.0`;
- cacheable Agent Card discovery at `/.well-known/agent-card.json`;
- required `A2A-Version: 1.0` HTTP negotiation;
- JSON-RPC `SendMessage`, `GetTask`, `ListTasks`, and `CancelTask`;
- durable task storage, status filtering, pagination, and bounded history;
- `INPUT_REQUIRED` interruption followed by same-task continuation;
- deterministic routing into the complete canonical skill/agent graph;
- terminal task failure containment;
- session-independent global skills on empty subject roots;
- loopback-only unauthenticated built-in HTTP transport with bounded request bodies.

See [`docs/A2A.md`](docs/A2A.md).

## Native evidence

Confirmed consequences and protocol tasks are stored under:

```text
.ggen-create/receipts/
.ggen-create/tasks/mcp/
.ggen-create/tasks/a2a/
```

Machine-readable admission includes:

```text
schemas/native-receipt.schema.json
schemas/native-task.schema.json
schemas/a2a-agent-card.schema.json
ontology/native-runtime.ttl
shapes/native-runtime.shacl.ttl
```

## Self-play

The bounded self-play rail attacks authority, confirmation, intent digests, path escape, no-op behavior, package corruption, autonomic repair, task transition law, TTL expiry, MCP lifecycle and durable tasks, A2A interruption/continuation, receipt tampering, and complete receipt-chain closure.

## Checkpoint ladders

### Parity

```text
P0–P7  hygen-create architectural and consequence parity
```

### Native

```text
N0 automatic plan
N1 automatic consequence + package integrity
N2 persistent automatic watch
N3 autonomic convergence and repair
N4 skill authority and Broker receipts
N5 agent topology and deterministic routing
N6 MCP lifecycle, tools, resources, and durable tasks
N7 A2A discovery, tasks, interruption, and continuation
N8 adversarial self-play
N9 receipt-ledger verification and evidence doctor
```

## Validation

```bash
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

GitHub Actions independently executes:

- the native CLI/protocol/SHACL/schema rail;
- the pinned real-ggen/original-hygen P7 crown.

## Current standing

```text
architecture and authority:          ADMITTED
deterministic parity implementation: IMPLEMENTED; exact-head crown required
automatic runtime:                   IMPLEMENTED; exact-head native run required
autonomic runtime:                   IMPLEMENTED; exact-head native run required
skill and agent authority:           IMPLEMENTED; ontology/code closure gate
MCP 2025-11-25 profile:              IMPLEMENTED; exact-head native run required
A2A 1.0 profile:                     IMPLEMENTED; exact-head native run required
adversarial self-play:               IMPLEMENTED; exact-head native run required
receipt graph and evidence doctor:   IMPLEMENTED; exact-head native run required
production network deployment:       UNKNOWN
multi-parameter structural synthesis: ROADMAP
self-hosting crown:                   NOT EXECUTED
```

Inspection, queued workflows, generated files, and implementation claims are not execution evidence.

## Canonical authority

1. [`AGENTS.md`](AGENTS.md)
2. [`product/PRD.md`](product/PRD.md)
3. [`architecture/ARD.md`](architecture/ARD.md)
4. [`docs/CHECKPOINTS.md`](docs/CHECKPOINTS.md)
5. [`docs/NATIVE_RUNTIME.md`](docs/NATIVE_RUNTIME.md)
6. [`docs/MCP.md`](docs/MCP.md)
7. [`docs/A2A.md`](docs/A2A.md)
8. [`docs/SKILLS_AND_AGENTS.md`](docs/SKILLS_AND_AGENTS.md)
9. [`ontology/ggen-create.ttl`](ontology/ggen-create.ttl)
10. [`ontology/native-runtime.ttl`](ontology/native-runtime.ttl)
11. [`shapes/ggen-create.shacl.ttl`](shapes/ggen-create.shacl.ttl)
12. [`shapes/native-runtime.shacl.ttl`](shapes/native-runtime.shacl.ttl)
