# Native Runtime

## Boundary

```text
working exemplar
→ deterministic parity core
→ automatic plan
→ confirmed Broker execution
→ admitted ggen package
→ receipt
```

`ggen-create` creates factories. The separate `ggen` CLI operates factories.

## Automatic mode

`automatic plan` inspects the capture, calculates a content fingerprint, and returns reversible candidate actions. It writes nothing.

`automatic run --confirm` manufactures the package, records the exact exemplar fingerprint, and emits a native receipt. Optional parity verification invokes the real `ggen` boundary in isolated staging.

`automatic watch` is bounded by an explicit cycle count. It executes only when the exemplar fingerprint changes and reports `STABLE` when no action is required.

## Autonomic mode

The autonomic controller is a bounded MAPE-K loop:

1. Monitor capture and package state.
2. Analyze absence, drift, stability, or missing input.
3. Plan a reversible action.
4. Execute only when `apply=true` and `confirm=true`.
5. Retain bounded knowledge and consequence receipts.

It stops on convergence, a typed block, or the configured cycle limit. It never retries forever.

## Authority

Skills and agents have `mayActuate=false`. They may SELECT or CONSTRUCT candidate intents. The Broker is the exclusive DO boundary.

Every write skill requires explicit confirmation. Every confirmed consequence receives a digest-verifiable receipt under `.ggen-create/receipts/`.

## Native standing rail

```text
N0 automatic plan
N1 confirmed automatic manufacture
N2 autonomic convergence
N3 skill authority closure
N4 bounded agent topology
N5 MCP lifecycle and tool consequence
N6 A2A discovery and task consequence
N7 adversarial self-play
N8 receipt verification
```

Protocol availability is not production deployment, external authentication, or general repository synthesis standing.
