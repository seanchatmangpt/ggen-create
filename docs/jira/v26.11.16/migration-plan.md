# ggen-create migration plan v26.11.16

Standing: UNVERIFIED

## Identity
- Path: /Users/sac/ggen-create
- Remote: https://github.com/seanchatmangpt/ggen-create
- Branch@sha: feat/rust-dspy-kernel-20260812@cc0dc4c [ahead 3], last 2026-11-09, 49 commits
- Size: 6 MB
- Languages/build: Rust workspace (Cargo.toml, crates/ggen-dspy, rust-toolchain.toml) +
  Python (pyproject.toml, scripts/enterprise_architecture_check.py)
- Nested repos: submodule `vendor/hygen-create` @124fac27 (ronp001/hygen-create v0.2.0)

## Observed state
- Dirty 0, untracked 9: all `docs/jira/` (this catalogue's own output).
- ahead 3 on the feature branch; main behind 6, feat/multi-seed-phase2 behind 3; stash 0.
- No target/ dir present. Submodule present and pinned.

## What it is
Creates deterministic ggen manufacturing packages from working examples; hosts the Rust DSPy
reasoning kernel (crates/ggen-dspy) with a hygen-create byte-parity contract.

## Classification
ACTIVE (census). Commits as recent as 2026-11-09.

## Migration risk
MEDIUM. 3 unpushed commits (cutover plan/dryrun work) on the feature branch would be lost.

## Recommended action
COMMIT-PUSH
1. `cd /Users/sac/ggen-create && git log origin/feat/rust-dspy-kernel-20260812..HEAD --oneline`
2. `git add docs/jira && git commit -m "docs: jira migration catalogue"`
3. `git push origin feat/rust-dspy-kernel-20260812`
4. `rm -rf target .venv`
5. Clone fresh with `--recurse-submodules` on the new machine.

## First commands on the new machine
`git submodule update --init && cargo check --workspace && python3 scripts/enterprise_architecture_check.py`

## See Also
- ../v26.9.19/
- /Users/sac/docs/jira/v26.11.16/README.md
