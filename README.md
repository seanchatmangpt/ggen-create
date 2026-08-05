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

`ggen-create` is create-time. `ggen` is construct-time. Skills and agents manufacture candidate graphs and intents; the Broker is the exclusive confirmed DO boundary.

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

The parity rail executes P0–P7: reference identity, bounded capture, lexical transformations, inspection, exact reconstruction, changed-parameter variation, revision behavior, and byte-exact original-reference comparison.

## Automatic mode

```bash
ggen-create automatic plan --output _ggen
ggen-create automatic run --output _ggen --confirm
ggen-create automatic watch --output _ggen --cycles 3 --confirm
```

Planning is reversible and writes nothing. Apply requires explicit confirmation, records the exemplar fingerprint, and emits a receipt.

## Autonomic mode

```bash
ggen-create autonomic run \
  --output _ggen \
  --max-cycles 4 \
  --stable-cycles 2 \
  --apply \
  --confirm
```

The controller is a bounded MAPE-K loop. It stops on convergence, a typed block, or the configured cycle ceiling. It never retries without bound.

## Skills and agents

```bash
ggen-create skills list
ggen-create agents list
ggen-create agents route "manufacture package"
ggen-create selfplay run --confirm
```

Eleven canonical skills and nine bounded agents are implemented. Every skill and agent declares `mayActuate=false`. Write skills require confirmation and cross the Broker boundary.

## MCP

```bash
ggen-create-mcp --root .
# or
ggen-create mcp serve --root .
```

Profile:

- protocol revision `2025-11-25`;
- stdio JSON-RPC transport;
- lifecycle, tools, resources, prompts, and durable task methods;
- nine tools;
- allowlisted resources only;
- confirmation on every write tool.

See [`docs/MCP.md`](docs/MCP.md).

## A2A

```bash
ggen-create a2a card
ggen-create-a2a --root . --host 127.0.0.1 --port 8765
```

Profile:

- protocol profile `1.0`;
- Agent Card discovery at `/.well-known/agent-card.json`;
- JSON-RPC `SendMessage`, `GetTask`, `ListTasks`, and `CancelTask`;
- durable task storage;
- deterministic routing into the canonical agent graph;
- loopback-only built-in HTTP transport.

See [`docs/A2A.md`](docs/A2A.md).

## Native receipts

Confirmed consequences are stored under:

```text
.ggen-create/receipts/
.ggen-create/tasks/mcp/
.ggen-create/tasks/a2a/
```

```bash
ggen-create receipt latest
ggen-create receipt verify
```

## Checkpoint ladders

### Parity

```text
P0–P7  hygen-create architectural and consequence parity
```

### Native

```text
N0 automatic plan
N1 automatic consequence
N2 autonomic convergence
N3 skill authority
N4 agent topology
N5 MCP consequence
N6 A2A consequence
N7 adversarial self-play
N8 receipt verification
```

## Validation

```bash
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

GitHub Actions independently executes the native protocol rail and the pinned real-ggen/original-hygen parity crown.

## Current standing

```text
architecture and authority:          ADMITTED
deterministic parity implementation: ALIVE in tests
automatic runtime:                   ALIVE in tests
autonomic runtime:                   ALIVE in tests
skill and agent authority:           ALIVE in tests
MCP 2025-11-25 profile:              ALIVE in tests
A2A 1.0 profile:                     ALIVE in tests
adversarial self-play:               ALIVE in tests
exact-head native workflow:          CI GATE
P7 real-ggen/original crown:          CI GATE
production network deployment:       UNKNOWN
self-hosting crown:                   NOT EXECUTED
```

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
