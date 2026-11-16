# ggen-create: land or delete remote branch `agent/bootstrap-ggen-create`

- Standing: OPEN
- Created: 2026-09-19 (v26.9.19 gh survey wave)
- Source: remote branch `agent/bootstrap-ggen-create` — not merged into `main`, no open PR
- Evidence: `git branch -r --no-merged origin/main` lists it; absent from `gh pr list` heads

## Work to complete
- Decide: open a PR (`gh pr create -R seanchatmangpt/ggen-create --head agent/bootstrap-ggen-create`) or delete (`git push origin --delete agent/bootstrap-ggen-create`).
- If superseded, delete; otherwise land through review.

## Acceptance
- After `git fetch --prune`, `git branch -r --no-merged origin/main` no longer lists `agent/bootstrap-ggen-create`.

## History
- 2026-09-19 | OPEN | survey found PR-less unmerged branch | agent/bootstrap-ggen-create | decision pending
