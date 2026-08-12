# Enterprise Readiness Gates

## Purpose

This document defines the evidence required to promote the Rust DSPy capability from repository implementation standing to an enterprise workload. It deliberately separates **library correctness** from **production service readiness**.

`ggen-dspy` can be `ALIVE` as a library while a particular production deployment remains `UNKNOWN`, `BLOCKED`, or `REFUSED`.

## Standing ladder

```text
SOURCE_OBSERVED
  ↓
ARCHITECTURE_ADMITTED
  ↓
IMPLEMENTATION_ALIVE
  ↓
INTEGRATION_ADMITTED
  ↓
ENVIRONMENT_ADMITTED
  ↓
RELEASE_ADMITTED
  ↓
PRODUCTION_ALIVE
```

No lower rung implies a higher rung.

## Gate 0 — exact subject identity

Required:

- repository identity;
- exact base revision;
- exact candidate revision;
- Rust toolchain identity;
- lockfile identity;
- architecture contract version.

Refuse when any identity is missing or moving.

## Gate 1 — architecture conformance

Required:

- `architecture/enterprise.toml` parses;
- ADR-0001 remains accepted or is explicitly superseded;
- `ggen-dspy` remains publish-disabled;
- `#![forbid(unsafe_code)]` remains present;
- runtime dependency count matches the admitted contract;
- no prohibited process/filesystem/network/FFI execution marker is present in Rust source;
- required typed authority markers remain present;
- enterprise architecture and readiness documents are present.

Failure standing: `BUILD_BROKEN:ENTERPRISE_ARCHITECTURE_CONFORMANCE_FAILED`.

## Gate 2 — implementation evidence

Required:

- `cargo fmt --all -- --check`;
- `cargo test --workspace --all-targets --locked`;
- repository product tests;
- exact-head CI admission;
- GALL crown.

A skipped Rust lane cannot produce Rust implementation standing.

## Gate 3 — integration admission

The integrating application must prove:

- the broker is the exclusive external actuation path;
- model output cannot directly invoke privileged code;
- credentials are unavailable to `ggen-dspy`;
- every action intent receives a stable correlation identity;
- policy decisions are explicit and inspectable;
- external actions are idempotent or carry a documented duplicate-effect strategy;
- broker results return typed evidence to the reasoning layer;
- failures cannot silently fall through to a less governed execution path.

Required artifact: workload-specific integration ADR.

## Gate 4 — security admission

Required for the deployed workload:

- threat model covering prompt injection, confused deputy, credential theft, data exfiltration, replay, dependency compromise, and unauthorized tool selection;
- data classification for prompts, retrieval material, tool arguments, outputs, and receipts;
- least-privilege identity design;
- secret storage and rotation policy;
- network egress policy at the broker boundary;
- audit retention policy;
- vulnerability management owner;
- dependency/SBOM policy for the host application;
- incident response runbook.

`ggen-dspy` itself is intentionally credential-free; this does not remove the obligation from the host/broker.

## Gate 5 — reliability and resilience admission

Required for any service wrapper:

| Objective | Required decision |
| --- | --- |
| Availability SLO | workload-specific target and measurement |
| Latency SLO | end-to-end and broker-specific budgets |
| Error budget | explicit policy |
| RTO | maximum acceptable restoration time |
| RPO | maximum acceptable receipt/state loss |
| Retry policy | bounded, classified, non-duplicating |
| Idempotency | key strategy or compensating control |
| Queue pressure | backpressure and overload behavior |
| Dependency failure | model/retriever/broker degraded mode |
| Regional failure | failover or explicit single-region acceptance |
| Replay | evidence that admitted requests can be reproduced safely |

No default RTO/RPO is asserted by this library.

## Gate 6 — observability admission

Minimum host telemetry:

- exact software revision;
- request/correlation identity;
- selected module/pattern;
- model/provider/config identity;
- intent digest;
- admission decision;
- broker target identity;
- execution receipt identity;
- typed outcome/standing;
- latency and resource measures.

Sensitive prompt/retrieval payloads are excluded from logs unless data policy explicitly admits them.

Required operational views:

- rate of intents manufactured;
- rate admitted/refused;
- external actuation success/failure;
- refusal reason distribution;
- retry and duplicate-suppression counts;
- latency percentiles;
- model/provider failure rate;
- broker saturation;
- receipt verification failures.

## Gate 7 — release governance

Required before production:

- change ticket / release record bound to exact candidate revision;
- architecture gate green;
- security admission green;
- integration tests against the actual broker adapter;
- rollback decision and tested mechanism;
- operational ownership/on-call assignment;
- production configuration reviewed separately from code defaults;
- evidence retention destination identified;
- known limitations and unsupported regions documented.

## Gate 8 — production standing

Production may be `ALIVE` only after the deployed exact artifact is observed and verified in the target environment.

A successful repository PR does not establish production standing.

## RACI

| Activity | Architecture | Product/Domain | Security | Platform/Broker | SRE/Operations |
| --- | --- | --- | --- | --- | --- |
| reasoning API design | A | R | C | C | I |
| authority boundary | A/R | C | A/C | R | I |
| tool/action policy | C | A | C | R | I |
| credentials | I | C | A | R | C |
| data classification | C | A/R | A/C | C | I |
| SLO/RTO/RPO | C | A | C | R | A/R |
| release admission | C | A | C | R | R |
| incident response | I | C | A/R | R | A/R |

`A` = accountable, `R` = responsible, `C` = consulted, `I` = informed. An adopter may change role names but must not collapse all decision rights into the reasoning component.

## Risk register

| Risk | Inherent severity | Primary treatment | Residual condition to monitor |
| --- | --- | --- | --- |
| model-generated privileged action | critical | broker-only DO | broker bypass attempts |
| prompt injection influences tool choice | high | policy admission + least privilege | abnormal refusal/admission patterns |
| generated code executes unsafely | critical | code-intent only in crate | broker executor sandbox quality |
| dependency compromise | high | zero Rust runtime deps at admission | host dependency drift |
| data leakage through telemetry | high | metadata-first logging | payload logging exceptions |
| duplicate side effects on retry | high | idempotency/receipt design | duplicate suppression failures |
| stale evidence grants standing | high | exact-head/revision binding | moving refs or stale receipts |
| reasoning layer self-certifies | high | external verifier/standing owner | boundary erosion |

## Production falsifiers

A workload must not claim `PRODUCTION_ALIVE` if any of the following is true:

- reasoning code can invoke external side effects without broker admission;
- production credentials are directly accessible to `ggen-dspy`;
- action receipts cannot be correlated to exact requests and software revisions;
- deployment identity differs from verified identity;
- security or resilience gates are skipped but inferred as passing;
- generated code can execute without a workload-specific sandbox/admission policy;
- rollback is undefined for a side-effecting release;
- monitoring cannot distinguish refusal, model failure, broker failure, and external-system failure.

## Exit criteria for this PR

For the repository scope of the Rust DSPy move, completion means:

1. architecture contract is present;
2. authority ADR is present;
3. enterprise architecture is documented;
4. architecture conformance is executable in CI;
5. Rust tests remain green;
6. exact-head CI is green after the architecture additions;
7. the PR remains draft unless explicitly promoted or merged by the owner.

That is **enterprise architecture closure for the repository capability**, not a claim that an unspecified Fortune-5 production workload has already been deployed.
