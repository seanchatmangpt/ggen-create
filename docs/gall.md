# GALL checkpoint contract

GALL is the promotion boundary between a candidate observation and an evidence-backed claim. No checkpoint begins `ALIVE`.

## State law

A successful checkpoint records exactly:

```text
CANDIDATE → ADMITTED → ALIVE
```

`ADMITTED` requires exact revision identity and a clean worktree. `ALIVE` additionally requires a positive witness, an executing negative falsifier that produces the expected typed refusal, deterministic subprocess replay, and receipt agreement.

A failed checkpoint terminates in a typed `REFUSED:*`, `BUILD_BROKEN:*`, or `UNSUPPORTED:*` standing. A crown containing any non-`ALIVE` checkpoint is `PARTIAL_ALIVE` and has no crown claim.

## Checkpoints

| Checkpoint | Positive witness | Negative falsifier |
| --- | --- | --- |
| `exact_head` | observed `HEAD` equals admitted revision | mismatched revision is refused |
| `clean_tree` | no tracked or untracked drift | dirty fixture repository is refused |
| `routing` | changed paths deterministically map to owned lanes | traversal path is refused |
| `ci` | tests, compilation, and workflow YAML parse | invalid Python is rejected |
| `docs` | required Markdown is UTF-8 and non-empty | empty Markdown is rejected |
| `ontology` | admitted ontology extensions and encoding | unknown ontology payload is rejected |
| `build` | Cargo evidence or bounded bootstrap absence | orphan build surface is rejected |
| `receipt` | schema, evidence, replay, and transition agreement | missing falsifier evidence is rejected |

## Receipt authority

Checkpoint receipts use `ggen-create.gall.checkpoint.v1`. The aggregate uses `ggen-create.gall.crown.v1`. The crown claim ceiling is `EXACT_HEAD_CLEAN_REPLAYED_CHECKPOINTS_ONLY`; it says nothing about capabilities that do not exist in the admitted tree.
