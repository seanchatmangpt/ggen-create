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
3. Prove deterministic `hygen-create` parity.
4. Add automatic planning and confirmed execution.
5. Add bounded autonomic convergence.
6. Project canonical skills and agents into protocols.
7. Execute adversarial self-play and verify receipts.
8. Extend only after the smaller rail is ALIVE.

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

Inspection is not execution. A generated skill file is not an admitted skill. An Agent Card is not an executed topology. A queued workflow is not evidence.

## Authority

### SELECT

May inspect and choose among admitted reversible candidates.

### CONSTRUCT

May manufacture candidate graphs, package files, verifier definitions, skills, agent roles, task requests, and intents.

### DO

May change filesystem state or execute processes only through the Broker. Zero unreceipted actuation.

All skills, agents, MCP endpoints, and A2A endpoints declare `mayActuate=false`. Write operations require explicit confirmation. The Broker verifies the intent, executes the bounded consequence, and emits a receipt.

## Automatic law

`automatic plan` is reversible and non-actuating.

`automatic run` requires confirmation. It fingerprints the admitted exemplar, manufactures the ggen package, optionally invokes real parity verification, writes controller state, and emits a receipt.

`automatic watch` must have a finite cycle ceiling and executes only on observed fingerprint change.

## Autonomic law

The controller is bounded MAPE-K:

```text
monitor → analyze → plan → confirmed execute → knowledge
```

It must stop on convergence, typed block, or cycle ceiling. No infinite recovery loop is permitted.

## MCP law

- profile `2025-11-25`;
- stdio JSON-RPC;
- lifecycle before capability use;
- allowlisted resources only;
- durable receiver-owned tasks;
- every write tool requires `confirm:true`.

## A2A law

- profile `1.0`;
- Agent Card is a projection of the canonical agent graph;
- deterministic goal routing;
- durable receiver-owned tasks;
- built-in unauthenticated HTTP transport is loopback-only;
- every write operation requires explicit confirmation.

## Two ladders

### Parity ladder

P0–P7 remains deterministic and agent-free. It compares real consequences from the original `hygen-create`/Hygen path and the ggen path.

### Native ladder

```text
N0 automatic plan
N1 automatic consequence
N2 autonomic convergence
N3 skill authority closure
N4 bounded agent topology
N5 MCP consequence
N6 A2A consequence
N7 adversarial self-play
N8 receipt verification
```

## Implementation discipline

- Resolve exact subject SHA before claims.
- Read root and nested doctrine before editing.
- Do not hand-edit generated outputs.
- Do not fabricate execution evidence.
- Do not weaken tests to obtain green status.
- Classify failed transitions before repair.
- Never rerun an unchanged failure without a new hypothesis.
- Default to a draft PR.
- Never merge unless explicitly requested.
- Protocol availability does not establish production authentication, deployment, or general repository synthesis.
