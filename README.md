# ggen-create

**Exemplar-to-ggen reverse compiler with Gall's-Law checkpoints.**

`ggen-create` observes working exemplars, manufactures a reusable ggen manufacturing package, and verifies that the separate `ggen` CLI reconstructs and varies those exemplars correctly.

> Create the factory. Admit the factory. Let ggen operate the factory.

## Architectural fence

```text
working exemplars
      ↓
ggen-create
      ↓
admitted ggen package
      ↓
ggen sync run
      ↓
artifacts + receipts
```

`ggen-create` is create-time. `ggen` is construct-time.

`ggen-create` does not render target artifacts itself. Its parity verifier invokes the public `ggen` executable inside isolated staging directories, then independently compares the resulting artifact projection.

## Current implementation

The deterministic parity slice is implemented as a dependency-free Python 3.11+ CLI. It deliberately uses no agents.

Implemented original-compatible commands:

```text
start
rename
add
remove / rm
usename
setopt
status / s
generate / g
abort
verify
compare
```

Equivalent native spellings are also available under:

```text
capture
parameter
package
parity
```

The implementation provides:

- original-compatible `ggen-create.json` capture state;
- upward session discovery;
- explicit bounded path admission;
- recursive directory capture;
- symlink, binary, non-UTF-8, missing-path, and outside-root refusals;
- lexical case-family anti-unification across paths and contents;
- mechanical status inspection;
- deterministic ggen package manufacture;
- unchanged-package no-op detection;
- changed-package revision archival;
- reconstruction and changed-parameter verification through the real `ggen` CLI;
- optional behavioral command verification;
- byte-exact comparison with an independently generated `hygen-create` reference tree;
- a machine-readable P0–P7 parity report.

## Install

```bash
python -m pip install -e .
ggen-create --help
```

No runtime Python dependencies are required.

## Original-compatible workflow

```bash
cd working-example

ggen-create start greeter
ggen-create add package.json dist/hello.js
ggen-create usename Hello
ggen-create status --verbose
ggen-create generate --output ../packages
```

The result is a ggen project:

```text
../packages/greeter/
├── ggen.toml
├── ontology.ttl
├── templates/
├── ggen-create-package.json
└── receipt.json
```

`ggen-create generate` creates the factory. It does not operate it.

## Real parity verification

```bash
ggen-create verify \
  --output ../verification \
  --ggen-bin /path/to/ggen \
  --set Hola \
  --check-command "npm run {lower}" \
  --stdout-contains "{capitalized}!" \
  --reference-dir /path/to/original-hygen-output \
  --reference-id "ronp001/hygen-create@0.2.1+hygen@1.6.2"
```

This executes:

```text
P0  reference identity
P1  bounded capture
P2  lexical transformations
P3  mechanical inspection
P4  exact Hello reconstruction
P5  Hello → Hola variation
P6  unchanged no-op + changed revision archive
P7  byte-exact original-reference comparison
```

The final report is written to:

```text
verification/parity-report.json
```

Without `--reference-dir` and `--reference-id`, the internal rail can reach `PARTIAL_ALIVE`, but not the original-reference crown.

## Architectural influence

The immediate influence is [`ronp001/hygen-create`](https://github.com/ronp001/hygen-create):

```text
existing working files
→ select files
→ seed a name
→ infer lexical transformations
→ preview
→ emit a reusable generator
```

The parity implementation preserves that flow and its capture-file shape. Its output, however, is a ggen package rather than a Hygen `_templates` directory.

[`seanchatmangpt/ggen-legacy`](https://github.com/seanchatmangpt/ggen-legacy) is the large enterprise specialization of the create-side problem: repository archaeology, authority reconstruction, replacement manufacture, behavioral closure, replay, and predecessor-retirement standing.

## Two checkpoint ladders

### 1. Parity ladder

The implemented deterministic rail proves the original `hygen-create` job. It uses fixed skills and no subagents.

### 2. ggen-native ladder

This begins only after exact-head parity CI is green:

1. canonical graph creation;
2. SHACL and authority admission;
3. native skill synthesis;
4. bounded subagent synthesis;
5. held-out self-play;
6. self-hosting and replay.

## Validation

Local deterministic validation:

```bash
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

GitHub Actions additionally builds the real `ggen` CLI, installs the original `hygen-create` and Hygen packages, manufactures both Hola artifacts independently, executes the generated program, and compares the artifact trees byte-for-byte.

## Standing

```text
architecture:                    ADMITTED
deterministic parity skills:     ALIVE locally
original-compatible CLI:         ALIVE locally
ggen package emission:           ALIVE locally
revision behavior:               ALIVE locally
real ggen reconstruction:        CI GATE
original hygen-create comparison: CI GATE
P7 exact-head parity crown:       UNKNOWN until workflow completion
ggen-native skills and agents:   NOT IMPLEMENTED
```

## Canonical authority

1. [`AGENTS.md`](AGENTS.md)
2. [`product/PRD.md`](product/PRD.md)
3. [`architecture/ARD.md`](architecture/ARD.md)
4. [`docs/CHECKPOINTS.md`](docs/CHECKPOINTS.md)
5. [`docs/PARITY_IMPLEMENTATION.md`](docs/PARITY_IMPLEMENTATION.md)
6. [`docs/SKILLS_AND_AGENTS.md`](docs/SKILLS_AND_AGENTS.md)
7. [`docs/CLI_CONTRACT.md`](docs/CLI_CONTRACT.md)
8. [`ontology/ggen-create.ttl`](ontology/ggen-create.ttl)
9. [`shapes/ggen-create.shacl.ttl`](shapes/ggen-create.shacl.ttl)
10. [`ROADMAP.md`](ROADMAP.md)
