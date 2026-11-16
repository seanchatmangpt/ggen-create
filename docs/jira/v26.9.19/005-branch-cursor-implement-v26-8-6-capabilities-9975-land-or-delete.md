# ggen-create: land or delete remote branch `cursor/implement-v26-8-6-capabilities-9975`

- Standing: OPEN
- Created: 2026-09-19 (v26.9.19 gh survey wave)
- Source: remote branch `cursor/implement-v26-8-6-capabilities-9975` — not merged into `main`, no open PR
- Evidence: `git branch -r --no-merged origin/main` lists it; absent from `gh pr list` heads

## Work to complete
- Decide: open a PR (`gh pr create -R seanchatmangpt/ggen-create --head cursor/implement-v26-8-6-capabilities-9975`) or delete (`git push origin --delete cursor/implement-v26-8-6-capabilities-9975`).
- If superseded, delete; otherwise land through review.

## Acceptance
- After `git fetch --prune`, `git branch -r --no-merged origin/main` no longer lists `cursor/implement-v26-8-6-capabilities-9975`.

## History
- 2026-09-19 | OPEN | survey found PR-less unmerged branch | cursor/implement-v26-8-6-capabilities-9975 | decision pending
