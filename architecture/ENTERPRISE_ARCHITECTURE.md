# Enterprise Architecture: ggen-create Rust DSPy Capability

## Executive architecture decision

`ggen-create` owns a Rust DSPy-inspired reasoning substrate as a bounded **SELECT / CONSTRUCT** capability. It does not own ambient **DO** authority. The enterprise boundary is deliberately asymmetric:

```text
untrusted/admitted inputs
        ↓
   ggen-dspy
 SELECT / CONSTRUCT
        ↓
 typed candidate intents
        ↓
  host broker / BRCE
 policy + identity + DO
        ↓
receipted external effect
        ↓
 verifier / standing
```

This is the target state for enterprise use. The architecture is optimized for auditability, deterministic replay, least privilege, and substitution of reasoning implementations without widening the execution trust zone.

## Architecture principles

1. **Authority is explicit.** A prediction, plan, tool request, or generated program is data until admitted by an execution authority.
2. **Zero unreceipted actuation.** External side effects exist only behind the broker boundary and must produce evidence.
3. **Exact identity before standing.** Repository, base, candidate head, toolchain, and execution evidence bind every acceptance claim.
4. **Determinism before intelligence.** Known transformations, bounded search, cached observations, and replayable computation precede model discretion.
5. **Small trusted computing base.** The reasoning crate has no runtime dependencies, forbids unsafe Rust, and has no direct process/filesystem/network actuation.
6. **Typed handoffs over conversational authority.** Cross-boundary transitions use `ActionIntent`, `ToolObservation`, `CodeIntent`, `ExecutionResult`, and explicit standing rather than implicit agent privileges.
7. **Evidence is a product surface.** Verification, receipts, refusal reasons, and falsifiers are first-class outputs.

## Business architecture

### Business capability enabled

The Rust DSPy layer provides a reusable decision-construction substrate for deterministic manufacturing workflows, forward-deployed engineering, repository reconstitution, and agent-assisted architecture work.

It supports:

- structured reasoning patterns;
- bounded candidate generation and optimization;
- retrieval-backed synthesis;
- deterministic evaluation;
- reusable agent patterns;
- typed tool/code intent manufacture;
- broker-mediated external execution.

### Business value boundary

The component does **not** claim production authority, business approval, release approval, or autonomous infrastructure control. Those capabilities remain outside the reasoning crate and require enterprise policy owners.

### Decision rights

| Decision | Owner |
| --- | --- |
| prompt/module construction | `ggen-dspy` |
| candidate optimization | `ggen-dspy` within configured bounds |
| model/provider selection | host/integrator |
| credential use | host broker |
| external side effect | host broker |
| admission policy | host broker / policy layer |
| receipt issuance | host broker |
| system standing | verifier/certifier |
| production release | owning enterprise release authority |

## Application architecture

### Component model

| Component | Responsibility | Trust posture |
| --- | --- | --- |
| `core` | signatures, values, LM/module contracts | pure construction |
| `modules` | Predict, CoT, ReAct, retrieval, multi-hop, Program of Thought | construct-only |
| `optimize` | bounded few-shot/MIPRO-style search | construct-only |
| `evaluate` | deterministic scoring/evaluation | evidence construction |
| `assertions` | hard/soft semantic guards | local control |
| `adapters` | provider-neutral request/response adaptation | no transport authority |
| `config` | explicit settings, cache, context, usage | process-local state |
| `patterns` | reusable composition catalog | construct-only |
| host broker | policy, credentials, actuation, receipts | trusted DO boundary |

### Integration contract

The preferred enterprise integration is a hexagonal boundary:

```text
Domain/application code
        ↓
LanguageModel / RetrieverBackend
        ↓
ggen-dspy reasoning modules
        ↓
ActionIntent / CodeIntent
        ↓
Broker port
        ↓
policy adapter → platform adapter → external system
        ↓
ToolObservation / ExecutionResult + receipt
```

Provider SDKs, cloud clients, Kubernetes clients, Terraform execution, shells, and filesystem mutation do not belong in `ggen-dspy`.

## Data architecture

### Data classes

| Data | Classification | Persistence owner |
| --- | --- | --- |
| signatures/config | admitted configuration | host |
| prompts/predictions | candidate reasoning data | host policy |
| retrieved passages | observed evidence | retriever/host |
| tool/code intents | candidate action data | broker |
| tool observations | execution evidence | broker |
| optimization receipts | reasoning evidence | host |
| execution receipts | authoritative side-effect evidence | broker |
| standing | certified result | verifier/certifier |

### Data minimization

The crate does not require durable storage. Cache and context are process-local abstractions. Enterprise persistence, encryption, retention, legal hold, residency, and PII controls are host responsibilities because only the host knows the data classification and jurisdiction.

### Provenance

The Rust surface is semantically descended from `seanchatmangpt/ggen@39c5d11d961a3143b228381e0ec208344e0054c6/crates/ggen-dspy`. The target intentionally severs obsolete workspace coupling and direct execution semantics.

## Technology architecture

### Runtime profile

- language: Rust;
- unsafe code: forbidden;
- runtime dependencies: zero at admission;
- publish: disabled;
- toolchain: repository-pinned;
- lockfile: required;
- CI: exact-head, path-owned admission plus Rust format/test rail;
- network/process/filesystem actuation from `ggen-dspy`: prohibited.

### Portability

Because provider/network SDKs are not compiled into the crate, the reasoning kernel is portable across cloud, on-premises, isolated, and regulated environments. Integration-specific authority remains outside the kernel.

## Security architecture

### Trust zones

```text
Zone 0: untrusted external/model/retrieval input
Zone 1: admitted reasoning inputs
Zone 2: ggen-dspy candidate construction
Zone 3: broker policy/admission
Zone 4: credentialed actuation
Zone 5: receipt/verifier/standing
```

No direct edge from Zone 2 to Zone 4 is permitted.

### Primary threats and controls

| Threat | Control | Falsifier |
| --- | --- | --- |
| prompt/model output triggers side effect | candidate intents only | direct callback/process/network execution appears in crate |
| generated code executes itself | `CodeIntent` only | interpreter/compiler/process invocation added |
| tool metadata becomes executable capability | data-only `Tool` | callback/function pointer stored by tool definition |
| dependency compromise | zero runtime dependencies at admission | dependency added without architecture review |
| memory-unsafe extension | `#![forbid(unsafe_code)]` | unsafe code compiles |
| hidden authority through SDK | no provider/cloud SDK in crate | transport dependency or socket/process API appears |
| evidence self-certification | standing owned externally | module can mark its own side effect authoritative |

### Secrets

The crate must never own cloud credentials, long-lived tokens, private keys, or secret-store clients. Secret retrieval and credential scoping belong to the broker/integration layer.

## Reliability and resilience architecture

`ggen-dspy` is a library, not a continuously available service, so service-level RTO/RPO do not attach directly to the crate. Enterprise hosts must set workload-specific objectives.

Library-level reliability objectives are:

- deterministic behavior for identical explicit inputs where the supplied model/retriever behavior is deterministic;
- bounded optimizer search;
- typed failures rather than silent fallback across authority boundaries;
- no requirement for ambient network, filesystem, process, clock, or randomness to exercise the reasoning kernel;
- replayable broker handoffs.

A broker or service wrapping the crate must independently define availability, latency, queueing, retries, idempotency, disaster recovery, and regional failover.

## Operability

### Required telemetry at the host boundary

The host should emit, at minimum:

- exact application/repository revision;
- model/provider identity and admitted configuration;
- module/pattern identifier;
- intent identifier and digest;
- policy/admission decision;
- external target identity;
- execution result;
- receipt identity;
- standing/refusal status;
- latency and resource usage;
- correlation/trace identifier.

Prompt or retrieved content should only be logged when allowed by data-classification policy.

### Failure taxonomy

Use typed outcomes rather than ambiguous success booleans:

```text
UNKNOWN
PARTIAL_ALIVE
ALIVE
BLOCKED
BUILD_BROKEN
UNSUPPORTED
REFUSED:<reason>
```

`REFUSED:ACTUATION_REQUIRES_BROKER` is the canonical local result when Program of Thought reaches an execution boundary without broker authority.

## Governance

### Architecture review triggers

The following require an explicit ADR and security review before admission:

- any Rust runtime dependency added to `ggen-dspy`;
- any direct network, filesystem, process, FFI, or unsafe capability;
- persistent storage inside the crate;
- credential handling;
- tool callbacks or embedded executors;
- generated-code execution;
- a change to broker ownership of receipts or standing;
- removal of exact-head or Rust execution evidence from CI.

### Change classes

| Change | Review class |
| --- | --- |
| pure API addition preserving authority boundary | normal engineering review |
| optimizer/module behavior change | engineering + evaluation review |
| dependency addition | architecture + supply-chain review |
| authority boundary change | architecture + security + explicit ADR |
| broker/receipt/standing change | architecture review board class |

## Control framework crosswalk

This is an architectural crosswalk, not a certification claim.

| Control objective | Implementation posture |
| --- | --- |
| least privilege | reasoning layer cannot actuate |
| separation of duties | construct and DO are different components |
| change control | exact-head CI and architecture gate |
| secure development | unsafe forbidden; zero runtime dependencies at admission |
| audit logging | broker receipt ownership |
| configuration management | pinned toolchain and lockfile |
| supply-chain risk | dependency-minimized kernel |
| incident containment | provider/credential authority outside reasoning kernel |
| traceability | typed intents/results plus exact revisions |

The same evidence can be mapped by an adopter into NIST CSF / 800-53, ISO 27001, SOC 2, PCI DSS, or internal control catalogs without claiming conformance merely from this repository.

## Deployment patterns

### Pattern A: in-process governed reasoning

Application and `ggen-dspy` run together; all side effects call an injected broker port. Appropriate for internal developer tooling and single-tenant systems where the host process itself is within the trusted application boundary.

### Pattern B: isolated reasoning service

`ggen-dspy` is hosted behind a service API with no production credentials. A separate broker service performs admitted actions. Appropriate where teams require strong network-level separation of reasoning and execution.

### Pattern C: offline/air-gapped construction

The kernel runs with deterministic or locally hosted model/retriever adapters and manufactures intents/packages for later review. No execution credentials are present. Appropriate for restricted environments and high-assurance change design.

## Target operating model

```text
Enterprise policy / architecture authority
                 ↓
         Admission policy
                 ↓
Product/domain → ggen-dspy → candidate intent
                 ↓
           broker / BRCE
                 ↓
       platform-specific DO
                 ↓
         immutable receipt
                 ↓
       verifier / certifier
                 ↓
        scoped standing
```

## Architecture standing

At the exact candidate revision, the Rust DSPy implementation can earn `ALIVE` only when code tests and the enterprise conformance gate both pass. The architecture documents themselves are `ADMITTED`; they become operational evidence only through the exact-head CI rail.

No statement in this document authorizes production deployment by itself. Production standing remains workload-, environment-, policy-, and receipt-specific.
