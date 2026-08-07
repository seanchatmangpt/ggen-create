# Phase 5: Minimal agent topology — design

## Context

`ROADMAP.md` gates Phase 5 ("Minimal agent topology") on Phase 1's external P7 crown
going green. That happened this session: `HYGEN_CREATE_PARITY_ALIVE` is now admitted
(`scripts/gall_p7_crown.py`, PC0–PC3 `ALIVE`, published under exact-head CI).

`receiver`, `correspondence-analyst`, and `admission-referee` already exist as registered
`AgentSpec`s in `src/ggen_create/agents.py` — named, skill-scoped, handoff-wired — and
`architecture/ARD.md`'s "Handoff topology" section names the typed artifacts that should
flow between them: `AdmittedRepositoryObservation`, `CandidateCorrespondenceGraph`,
`AdmissionDecision`. None of that behavior exists in code. The deterministic router
(`AgentRuntime.route()`) can reach `receiver` but has zero keyword rules reaching
`correspondence-analyst` or `admission-referee` — they exist only as directly-dispatchable
agents today. `ROADMAP.md` is explicit that Phase 5 requires "held-out replay evidence"
before any further agent may be introduced, and `product/PRD.md`/`architecture/ARD.md`
have no behavioral spec beyond agent names, skill scoping, and the typed-artifact-flow
diagram — this is genuinely greenfield on the semantics.

This spec closes that gap: real typed artifacts, real admission-decision logic, and real
held-out replay evidence against a genuine external subject — not just wiring three
already-registered agents together.

## Decisions made during brainstorming

- **Depth**: real typed artifacts + real decision logic, not a thin wrapper over existing
  generic checks. Matches ARD's own diagram rather than settling for less.
- **Held-out subject**: `ggen-create`'s own repository. Not a separate synthetic case —
  the topology examines the very codebase it's built into. This leans toward Phase 9
  (self-hosting) in spirit, but is a legitimate and arguably stronger proof: real,
  non-fixture, non-tuned-against subject.
- **Observation primitive**: `plan_legacy_factory()` (`src/ggen_create/legacy_model.py`,
  the function underlying the existing `legacy.plan` skill), already built and reused
  directly. It's purpose-fit for "bounded manifest of an arbitrary repository, no seed or
  captured session required" — a better match than forcing `receiver`'s existing
  `capture.inspect` skill (which needs a hygen-create-style captured session: a seed word
  plus an explicit file set) onto a ~50-file Python repository. `receiver` gets a new
  `topology.observe` skill that calls `plan_legacy_factory()` directly and wraps the
  result into `AdmittedRepositoryObservation`, rather than dispatching through the
  existing `legacy.plan` skill — that skill's own dispatch returns a raw manifest dict
  scoped to `ggen-legacy`'s receiving-bundle flow, not the typed artifact this topology
  needs.
- **Correspondence approach**: digest-correspondence, not category-correspondence.
  `correspondence-analyst` re-walks the subject and diffs recomputed digests against the
  recorded observation, reusing the `equal`/`only_left`/`only_right`/`different` shape
  already used three times this session (`compare_reference_trees`, package verify, the
  submodule parity SM2 checkpoint). Rejected alternative: semantic structural checks
  (every source file has a test, every skill has a dispatch branch) — richer claims, but
  more arbitrary to define correctly and a worse fit for "minimal."

## Architecture / data flow

```
receiver.dispatch("receiver", "topology.observe", {subject_root: <ggen-create repo root>})
  → plan_legacy_factory(subject_root)  [existing, unmodified]
  → AdmittedRepositoryObservation      [receiver's typed output]

correspondence-analyst.dispatch("correspondence-analyst", "correspondence.analyze", {observation: ...})
  → re-walk subject_root, recompute every file's sha256 fresh
  → diff against observation.manifest["files"] (equal/only_left/only_right/different shape)
  → CandidateCorrespondenceGraph       [correspondence-analyst's typed output]

admission-referee.dispatch("admission-referee", "admission.decide", {graph: ..., observation: ...})
  → standing = "REFUSED" if graph.equal is False (drift = hard gate)
             = "PARTIAL_ALIVE" if equal but observation.manifest["blockers"] is non-empty
             = "ADMITTED" if equal and no blockers
  → AdmissionDecision                  [admission-referee's typed output, terminal]
```

Each hop is a normal `AgentRuntime.dispatch()` call through the existing `Broker` — no new
control-flow machinery. Receipted at each DO-authority step, matching existing convention
(`skills.py`'s `Broker.execute`).

## Typed artifacts — new module `src/ggen_create/topology.py`

Plain dataclasses, `asdict()`-serializable, matching the codebase's existing style
(`legacy_model.py`, `verify.py`):

```python
@dataclass
class AdmittedRepositoryObservation:
    schema: str  # "ggen-create-topology-observation/1"
    manifest: dict   # plan_legacy_factory()'s output, unmodified
    observed_at_digest: str  # manifest["subject"]["digest"], hoisted for convenience

@dataclass
class CandidateCorrespondenceGraph:
    schema: str  # "ggen-create-topology-correspondence/1"
    equal: bool
    only_left: list[str]
    only_right: list[str]
    different: list[str]
    checked_files: int

@dataclass
class AdmissionDecision:
    schema: str  # "ggen-create-topology-admission/1"
    standing: str  # "ADMITTED" | "PARTIAL_ALIVE" | "REFUSED"
    reasons: list[str]  # blockers + drift entries, empty when ADMITTED
```

Reuse `digest_file`/`digest_json`/`require_under` from `src/ggen_create/runtime.py` for the
correspondence re-walk, the same helpers `legacy_model.py` and `verify.py` already use.

## Skills (`src/ggen_create/skills.py`)

- New `SkillSpec("topology.observe", authority="CONSTRUCT", requires_confirmation=False, requires_session=False, ...)` — calls `plan_legacy_factory()` directly, wraps into `AdmittedRepositoryObservation`.
- New `SkillSpec("correspondence.analyze", authority="CONSTRUCT", requires_confirmation=False, requires_session=False, ...)` — pure inspection, no actuation.
- New `SkillSpec("admission.decide", authority="SELECT", requires_confirmation=False, requires_session=False, ...)` — a verdict, not actuation.
- `receiver`'s skill tuple gains `topology.observe`.
- `correspondence-analyst`'s skill tuple gains `correspondence.analyze`.
- `admission-referee`'s skill tuple gains `admission.decide`.
- Three new `Broker._dispatch` branches calling into `topology.py`'s functions, following
  the existing dispatch-table pattern.

## Router (`src/ggen_create/agents.py`)

Both `correspondence-analyst` and `admission-referee` are currently dead ends in the
deterministic router (only reachable via direct `plan()`/`dispatch()` with an explicit
agent name). Add two rules to the `routes` tuple in `AgentRuntime.route()`
(`src/ggen_create/agents.py`), checked against every existing rule for collisions —
none of the keywords below appear in any current rule's token set:

```python
(
    ("correspondence", "analyze candidate"),
    "correspondence-analyst",
    "correspondence.analyze",
),
(
    ("admission", "admit", "refuse candidate"),
    "admission-referee",
    "admission.decide",
),
```

## Held-out replay evidence

**`tests/test_topology.py`** (new — no `test_agents.py`/`test_skills.py` exists today;
follows the direct-unit-test convention already used for `legacy_bundle.py`/`verify.py`):
unit tests for each of the three `topology.py` functions — happy path, drift detection,
blockers detection.

**`selfplay.py` scenarios** (integration/held-out layer, run against `ggen-create`'s own
repo root as subject — genuinely external, not a fixture):

1. Two independent full chain runs (receiver → correspondence-analyst → admission-referee)
   produce identical `AdmissionDecision` digests — determinism/replay, mirroring the G7
   replay-crown pattern in `scripts/gall_hygen_parity.py`.
2. Real, non-forced outcome assertion: `ggen-create`'s repo genuinely lacks `AGENTS.md`
   and `RELEASE_CONTROL.md` (`plan_legacy_factory`'s `authority` block checks for those
   exact filenames — `ggen-legacy`'s naming convention; `ggen-create` uses `CLAUDE.md`),
   so assert `standing == "PARTIAL_ALIVE"` with those two blockers named. This is an
   honest finding from a real subject, not a rigged happy path — if a future commit adds
   `AGENTS.md`/`RELEASE_CONTROL.md` to `ggen-create`, this assertion should be revisited,
   not silently left stale.
3. Tamper scenario: mutate one recorded file digest between the `receiver` and
   `correspondence-analyst` hops, assert `CandidateCorrespondenceGraph.equal is False` and
   `AdmissionDecision.standing == "REFUSED"` — mirrors the tamper-detection pattern used
   pervasively elsewhere in `selfplay.py` and the test suite.
4. Router-determinism checks for the two newly-reachable agents, mirroring the existing
   `manufacturing-architect` route-determinism check (`selfplay.py:164-172`).

## Error handling

Every new function raises `GgenCreateError` with a typed refusal code on malformed input,
matching existing convention — e.g. `CORRESPONDENCE_SUBJECT_MISSING_REFUSED` if the subject
root vanished between hops, `TOPOLOGY_OBSERVATION_SCHEMA_MISMATCH_REFUSED` if
`correspondence.analyze` receives a malformed observation dict. No new exception hierarchy.

## Files touched

- **New**: `src/ggen_create/topology.py`, `tests/test_topology.py`
- **Edited**: `src/ggen_create/skills.py` (3 new `SkillSpec`s, 3 new `Broker._dispatch`
  branches, 3 agents' skill tuples), `src/ggen_create/agents.py` (router keyword rules),
  `src/ggen_create/selfplay.py` (4 new scenarios)

## Verification

1. `python3 -m unittest discover -s tests -p 'test_topology.py' -v` — new unit tests green.
2. `python3 -m unittest discover -s tests -v` — full suite green, no regressions.
3. Run `selfplay.run` (via CLI or directly) — confirm the 4 new scenarios pass, including
   the real `PARTIAL_ALIVE` blockers finding against `ggen-create`'s own repo.
4. Confirm `agents.route("analyze correspondence")` resolves to `correspondence-analyst`/
   `correspondence.analyze`, and `agents.route("admit candidate")` resolves to
   `admission-referee`/`admission.decide` — both previously raised
   `AGENT_ROUTE_UNSUPPORTED`.
5. Update `ROADMAP.md`'s Phase 5 state line from "introduce only after..." to reflect
   admission — only after the above is verified green, not preemptively (same discipline
   used for the P7 crown status update earlier this session).

## Explicitly out of scope

- Any additional agent beyond the three already registered — `ROADMAP.md` is explicit:
  "No additional agents until this topology has held-out replay evidence."
- Wiring this topology into CI. Like the P7 crown and submodule parity checkpoints, this
  stays a local/selfplay-level capability for now; CI wiring (if warranted) is a separate,
  later decision once the topology itself has real evidence behind it.
- Changing `capture.inspect`'s or `legacy.plan`'s existing behavior, dispatch, or callers
  — `topology.observe` is a new, additive skill that reuses `plan_legacy_factory()` as a
  function call, not a change to either existing skill.
- Category/semantic correspondence checks (rejected alternative, see Decisions above).
