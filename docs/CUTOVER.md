# CUTOVER

Standing: PARTIAL

`ggen-create cutover` flips a declared set of `KEY=value` lines from a legacy backend to a
target backend, and can flip them back. It is the actuation half of a switch-over; it does not
retire anything. Claim ceiling: TESTED for the commands below. Nothing here is ALIVE or
PRODUCTION_PROVEN, and `release_admitted` / `sunset_admitted` stay false until ggen-legacy
admits them.

## Inputs (in the subject root)

- `cutover-prerequisites.json`: six booleans, all must be `true`: `migrations_applied`,
  `auth_bridge_configured`, `tripwire_green`, `release_admitted`, `two_probe_identity`,
  `write_freeze_declared`. Each false value has its own typed refusal (for example
  `PREFLIGHT_RELEASE_NOT_ADMITTED_REFUSED`) carrying `broken_term=<key>`.
- `cutover-targets.json` (schema `schemas/cutover-targets.schema.json`): `targets[]` of
  `{file, key, from, to}` plus optional `predecessors[]`, directory names a target may never
  live under.

## Commands

| Command | Authority | Effect |
|---|---|---|
| `cutover plan` | CONSTRUCT | preflight, targets hold `from`, sealed plan, no writes |
| `cutover power --confirm` | DO_INTENT | all-or-nothing flip, backups, atomic, receipt |
| `cutover verify [--replay]` | SELECT | standing; `--replay` refuses on drift |
| `cutover rollback --confirm` | DO_INTENT | byte-exact restore; refuses on drift |
| `cutover dryrun` | SELECT | read-only readiness probes for v26.11.9 tickets |

`power` and `rollback` refuse without `--confirm` (`ACTUATION_CONFIRMATION_REQUIRED_REFUSED`).
Failures write a `BLOCKED` receipt to the hash-chained receipt store, and
`ggen-create receipt chain` verifies the chain after any sequence.

## Refusal codes

`TARGETS_MISSING_REFUSED`, `TARGETS_SCHEMA_REFUSED`, `TARGET_PATH_ESCAPE_REFUSED`,
`TARGET_SYMLINK_REFUSED`, `TARGET_IN_PREDECESSOR_REFUSED`, `TARGET_VALUE_MISMATCH_REFUSED`,
`TARGET_KEY_MISSING_REFUSED`, `TARGET_KEY_AMBIGUOUS_REFUSED`, `ALREADY_POWERED_REFUSED`,
`NOTHING_TO_ROLL_BACK_REFUSED`, `TARGET_DRIFT_REFUSED`, `BACKUP_INTEGRITY_REFUSED`,
`REPLAY_DRIFT_REFUSED`, `POWER_ABORTED_ROLLED_BACK` (a mid-flip failure restored every file).

## Not in scope

- Deleting, archiving or decommissioning any backend. `cutover.py` has no such path; sunset is
  a separate, separately authorized actuation (ggen-legacy `RELEASE_CONTROL.md`).
- Starting or stopping services, migrating databases, or moving data.

## Dry run

`ggen-create cutover dryrun [--ticket T-NNN] [--selftest] [--home DIR] [--receipt FILE]`
scores tickets with clauses over files under `--home` (default `$HOME`):

- tier T0 clauses are decided from files; T1 (scratch run) and T2 (live backend) clauses stay
  `UNVERIFIED` and cap the verdict at `READY_TO_REHEARSE_PENDING_T1_T2`.
- `--selftest` mutates every deterministic clause and requires it to flip; a clause that does
  not exits non-zero as `VACUOUS_DRYRUN`.
- the run never executes repository scripts. Only `bash -n` and a Python syntax parse are
  allowlisted, because a script that predates a flag ignores it and runs for real.
- read-only proof: a stat digest of every file read, taken after evaluation and again after
  the self-test; a change yields `BLOCKED:UNSTABLE_EVIDENCE`.
- the report validates against `schemas/cutover-dryrun-report.schema.json`
  (`schema_validation` field). It is not a dfcm v2 receipt: that shape requires work-order and
  provider fields a dry run does not have.

Exit code is 0 only for a `READY...` verdict.

## See Also

`docs/GGEN_LEGACY.md` · ggen-legacy `docs/jira/v26.11.9/CHARTER.md` ·
ggen-legacy `RELEASE_CONTROL.md`
