# ADR-0001: Rust DSPy is CONSTRUCT-only

- **Status:** Accepted
- **Date:** 2026-08-12
- **Decision owner:** ggen-create architecture authority
- **Scope:** `crates/ggen-dspy`

## Context

The recovered Rust DSPy implementation provides typed prompting, modules, ReAct, retrieval, Program of Thought, optimization, evaluation, assertions, adapters, cache/context, usage tracking, and reusable agent patterns. The historical implementation was coupled to the former `ggen` workspace and exposed direct execution seams that are incompatible with `ggen-create`'s current authority model.

For a Fortune-5 deployment boundary, the critical question is not whether an LLM can propose an action. It is which component possesses authority to cause an external side effect and which evidence proves that authority was lawfully exercised.

## Decision

`ggen-dspy` is a **reasoning and construction substrate**, not an actuator.

It may:

- inspect admitted inputs;
- select among bounded candidate alternatives;
- construct prompts, predictions, plans, retrieval requests, tool intents, code intents, optimization candidates, and evaluation evidence;
- consume broker-returned observations and execution results.

It may not:

- spawn processes;
- access the filesystem for actuation;
- open network sockets;
- execute tool callbacks;
- execute generated code;
- grant standing to its own output;
- create an unreceipted external side effect.

The host broker is the exclusive **DO** authority. It owns admission, policy, identity, credentials, side effects, receipts, replay, and standing.

## Consequences

### Positive

1. Model output remains candidate data rather than authority.
2. ReAct and Program of Thought can be used in high-trust environments without embedding ambient execution capability in the reasoning crate.
3. Every external action can be independently policy-checked and receipt-bound.
4. The reasoning layer can be tested deterministically without cloud credentials, network access, or mutable infrastructure.
5. The crate has a deliberately narrow software-supply-chain surface: no runtime dependencies and no unsafe code.

### Costs

1. Integrators must provide a broker adapter to perform useful external actions.
2. Tool execution requires an additional typed handoff.
3. Some historical DSPy ergonomics that combine reasoning and direct execution are intentionally not preserved.

These costs are accepted because authority separation is a stronger enterprise invariant than API convenience.

## Control mapping

| Enterprise concern | Architectural control | Evidence |
| --- | --- | --- |
| Privilege containment | no ambient process/filesystem/network authority | `architecture/enterprise.toml` + conformance gate |
| Supply-chain minimization | zero Rust runtime dependencies | `crates/ggen-dspy/Cargo.toml` |
| Memory safety | unsafe Rust forbidden | crate root attribute + conformance gate |
| Change governance | exact-head CI | repository admission workflow |
| Auditability | broker owns receipts and standing | typed intent/result boundary |
| Determinism | bounded search, explicit values, no required ambient randomness | tests + architecture contract |
| Separation of duties | SELECT/CONSTRUCT distinct from DO | ARD + this ADR |

## Required invariants

A change to `ggen-dspy` is architecture-breaking unless explicitly superseded by a new ADR when any of the following becomes true:

- the crate gains direct process, filesystem, or network actuation;
- a `Tool` stores an executable callback rather than tool metadata;
- generated code is executed inside the crate;
- unsafe Rust is admitted;
- runtime dependencies are added without supply-chain review;
- model output can directly grant itself execution authority or standing;
- the broker boundary becomes optional for external side effects.

## Rejected alternatives

### Preserve historical direct execution

Rejected. It would collapse planning and authority into one trust zone and make receipts a logging concern rather than an admission boundary.

### Move all reasoning into the broker

Rejected. It would make the authority service larger, harder to audit, and harder to deterministically test. The broker should remain a small policy and actuation kernel.

### Permit actuation behind feature flags

Rejected for this crate. Feature flags can change a compile-time capability boundary invisibly to downstream architecture. External actuation belongs in a separately governed component.

## Supersession law

This ADR may be superseded only by an explicit ADR that identifies the new trust boundary, threat model, policy owner, receipt schema, rollback strategy, and migration path. Silent erosion of the boundary is not an accepted architecture change.
