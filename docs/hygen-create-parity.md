# Hygen-create example and documentation parity

## Admitted reference

This contract is pinned to:

```text
repository: ronp001/hygen-create
ref:        master
commit:     124fac27df0ddbc498b841ba3e05997ed10e4c39
tree:       bf088a9e2ab533cd9ba035ecddb0c31f30e292bd
```

The four files under `examples/hygen-create-reference/` preserve the upstream `example/` bytes exactly:

```text
hygen-create.json
package.json
dist/hello.js
test_strings.json
```

`parity.json` binds each file to its upstream Git blob identity. The verifier recomputes those identities before it admits any semantic claim.

## Why this fence exists

The upstream example is not decorative documentation. It defines the smallest working system:

1. capture a working project;
2. admit a bounded file set;
3. select `Hello` as the parameter seed;
4. inspect the planned replacements;
5. generate a reusable generator;
6. instantiate it with `Hola`;
7. execute the resulting package;
8. preserve an identical rerun and archive only a changed revision.

Removing or simplifying any of those transitions would weaken the behavioral contract. The ggen implementation may use a different package format, query language, or renderer, but it must preserve the same observable example consequences.

## Canonical ggen-create session

Start from `examples/hygen-create-reference/`:

```sh
ggen-create start greeter
ggen-create add package.json dist/hello.js
ggen-create usename Hello
ggen-create status
ggen-create generate
```

The expected capture remains structurally aligned with the original six-field session:

```json
{
  "about": "This is a hygen-create definitions file. The hygen-create utility creates generators that can be executed using hygen.",
  "hygen_create_version": "0.2.0",
  "name": "greeter",
  "files_and_dirs": {
    "hygen-create.json": true,
    "package.json": true,
    "dist/hello.js": true
  },
  "templatize_using_name": "Hello",
  "gen_parent_dir": false
}
```

The legacy field names are preserved in the reference fixture because they are part of the upstream generated consequence. A future ggen-native capture may project additional canonical data, but it must not corrupt this parity fixture.

## Using the generated package

The ggen-side invocation mirrors the Hygen example:

```sh
mkdir -p /tmp/hola-greeter
cd /tmp/hola-greeter
ggen greeter new --name Hola
npm run hola
```

The manufactured project must contain:

```text
package.json
hygen-create.json
dist/hola.js
```

`package.json` must name the package `hola` and expose this script:

```json
{
  "hola": "node dist/hola.js"
}
```

`dist/hola.js` must contain the transformed path reference and print:

```text
Hola!
```

## Case-family contract

The upstream `test_strings.json` corpus is executable evidence, not prose. It covers:

- lowercase, capitalized, and uppercase values;
- underscore and dash boundaries;
- PascalCase and lower camelCase;
- snake_case, UPPER_SNAKE_CASE, and kebab-case;
- suffix preservation;
- the negative `ClsWord` case, where an alphanumeric left neighbor prevents replacement.

The Gall verifier executes all 24 comparisons. A new implementation that handles only the greeter happy path cannot pass the case-family checkpoint.

## Revision and replay law

An identical rerun produces no changed revision. When the admitted source changes, the current generator is archived before replacement; the first archive is `greeter.1`. The verifier currently proves deterministic identical replay by manufacturing the Hola projection twice and comparing the complete path-and-byte tree digest.

The full changed-source archive consequence remains a product-runtime acceptance boundary. Documentation parity does not claim that the runtime exists on `main`.

## Gall checkpoints

| Checkpoint | Object | Required consequence |
| --- | --- | --- |
| G0 | reference identity | exact repository, commit, and tree |
| G1 | reference blobs | four byte-exact upstream example files |
| G2 | capture contract | ordered fields, generator, seed, file set, parent policy |
| G3 | case corpus | all 24 transformation examples match |
| G4 | documentation | commands, paths, output, and revision facts remain bound |
| G5 | reconstruction | `Hello` reconstructs the three captured files byte-exactly |
| G6 | variation | `Hola` creates `dist/hola.js` and `npm run hola` prints `Hola!` |
| G7 | replay crown | two independent manufactures have the same tree digest |

Run them directly:

```sh
python3 scripts/gall_hygen_parity.py \
  --root . \
  --receipt gall-hygen-parity-receipt.json
```

Run the unit binding:

```sh
python3 -m unittest discover -s tests -p 'test_parity_*.py' -v
```

The verifier receipt claim ceiling is `EXAMPLE_DOCUMENTATION_AND_LOCAL_REFERENCE_CONSEQUENCE_ONLY`. It does not establish the future ggen-create CLI, external ggen execution, arbitrary repository synthesis, or release standing.

## Live submodule validation (opt-in)

G0-G7 above prove that the vendored fixture files
(`examples/hygen-create-reference/*`) are internally consistent with their own hash
manifest. That is not the same as proving those fixtures still match a live, working
copy of upstream `hygen-create` — the fixtures and the manifest were copied together, so
G0/G1 cannot by themselves catch drift between the two.

`vendor/hygen-create` is the real `ronp001/hygen-create` repository, vendored as a git
submodule pinned to the same commit (`REFERENCE_COMMIT`,
`124fac27df0ddbc498b841ba3e05997ed10e4c39`) that G0 already asserts. Four checkpoints,
`scripts/gall_submodule_parity.py`, corroborate parity against that live checkout:

| Checkpoint | Object | Required consequence |
| --- | --- | --- |
| SM0 | submodule identity | checked-out commit equals `REFERENCE_COMMIT` |
| SM1 | upstream test suite | upstream's own `install`/`build`/`test` all succeed at that commit |
| SM2 | live blob match | the submodule's live `example/*` files are still byte-identical to the static fixtures |
| SM3 | live reconstruction | ggen-create's transform logic reconstructs `Hello`/`Hola` from the *live* submodule tree, not the static copy, byte-exactly |

This is deliberately **not** part of the G0-G7 crown, the default GALL crown, or CI: it
requires `git submodule update --init vendor/hygen-create` plus Node/npm/yarn and network
access to install and build the upstream project. Its receipt's claim ceiling is
`SUBMODULE_LIVE_CONSEQUENCE_ONLY` — it corroborates, but does not itself promote,
`HYGEN_CREATE_PARITY_ALIVE` or any GALL-admitted standing.

Run it directly:

```sh
git submodule update --init vendor/hygen-create
python3 scripts/gall_submodule_parity.py \
  --root . \
  --receipt submodule-parity-receipt.json
```

Run the unit binding (SM0/SM2/SM3 only — SM1 needs network and is not exercised by the
default unit run):

```sh
python3 -m unittest discover -s tests -p 'test_submodule_parity.py' -v
```

If the submodule is not initialized, `test_submodule_parity.py` skips cleanly rather than
failing, so the default `unittest discover` run stays green and network-free either way.

Known finding from running SM1 against the pinned commit: upstream's own 2018-era test
suite uses `mock-fs`, which is incompatible with modern Node.js (`fs` internals it
monkey-patches have since changed) — `tsc` builds cleanly, but `jest` fails a majority of
suites under current Node. This is a real, typed result about the upstream project's test
tooling, not a ggen-create defect, and is exactly the kind of drift this checkpoint exists
to surface rather than hide.

## Real-`ggen`-binary validation (opt-in)

Every checkpoint above — G0-G7 and SM0-SM3 — either compares static fixtures against a
manifest, or reconstructs trees with ggen-create's own Python transform logic
(`manufacture()`). None of them invoke a real `ggen` binary. `src/ggen_create/verify.py`'s
P0-P7 pipeline has real-binary support (`_run_ggen` shells out to `ggen_bin`), but nothing
in the repo had ever exercised it — README/ROADMAP/PRD all mark
`real public ggen parity crown (P7)` as `UNKNOWN`, and no `ggen` binary is provisioned
anywhere in this repo or its CI.

`scripts/gall_ggen_binary_parity.py` closes that specific, narrow gap: it builds a real
ggen-create session from the live `vendor/hygen-create` submodule, then calls
`verify_parity` against a real `ggen` binary on the machine running it.

| Checkpoint | Object | Required consequence |
| --- | --- | --- |
| GB0 | binary availability | a real `ggen` binary resolves and reports a version |
| GB1 | session capture | a ggen-create session is captured from the live submodule example |
| GB2 | real sync run | `verify_parity` reaches `P6_REVISION_PARITY: ALIVE` against the real binary, with `P7_PARITY_CROWN` correctly staying `PARTIAL_ALIVE` (no crown claimed) |
| GB3 | report shape | `parity-report.json` is actually written and its `ggen.binary`/`ggen.sync_args` fields reflect the real subprocess invocation |

**This does not close the P7 crown.** `P7_PARITY_CROWN: ALIVE` additionally requires a
`reference_dir` produced by the real upstream `hygen` render step — a separate npm package
from `hygen-create`, which only captures and templatizes, not renders. That's a
materially larger follow-on than "run the ggen binary once" and is deliberately not
attempted here. See `ROADMAP.md`'s "80/20 ERRC" section for how this is scoped.

Opt-in like the submodule checkpoint above: requires both `vendor/hygen-create`
initialized and a real `ggen` binary on `PATH` (or `$GGEN_BIN`). Not part of the default
GALL crown or CI.

Run it directly:

```sh
git submodule update --init vendor/hygen-create
python3 scripts/gall_ggen_binary_parity.py \
  --root . \
  --receipt ggen-binary-parity-receipt.json
```

Run the unit binding:

```sh
python3 -m unittest discover -s tests -p 'test_ggen_binary_parity.py' -v
```

If either the submodule or a real `ggen` binary is missing, `test_ggen_binary_parity.py`
skips cleanly rather than failing.

## Real P7 crown: `HYGEN_CREATE_PARITY_ALIVE` (`scripts/gall_p7_crown.py`)

`gall_ggen_binary_parity.py` above proved P0-P6 against a real `ggen` binary but
deliberately stopped short of P7 — that additionally requires a `reference_dir` produced
by the real upstream **`hygen`** render step (the separate npm package from
`hygen-create`, which only captures/templatizes, not renders). `scripts/gall_p7_crown.py`
closes that gap:

| Checkpoint | Object | Required consequence |
| --- | --- | --- |
| PC0 | hygen-create CLI build | a real `hygen-create` CLI builds from the live submodule (hermetic yarn install/build) |
| PC1 | template generation | `hygen-create generate` produces real Hygen `.ejs.t` templates from the submodule's captured example session |
| PC2 | real hygen render | the independent `hygen` renderer (`npx hygen greeter new --name Hola`) renders the Hola variant — a tool never previously exercised by this repo |
| PC3 | P7 crown | `verify_parity`, called against a real `ggen` binary with that rendered tree as `reference_dir`, reaches `P7_PARITY_CROWN: ALIVE` with a byte-exact, zero-drift `reference_comparison` |

This is the actual evidence `product/PRD.md`'s `HYGEN_CREATE_PARITY_ALIVE` gate describes:
real `ggen-create` CLI, real `ggen` binary reconstructing `Hello` and generating `Hola`,
and the original `hygen-create`/`hygen` toolchain independently generating `Hola` for
cross-rail comparison — all in one run, byte-exact, first try.

Opt-in like the checkpoints above: requires the submodule, a real `ggen` binary, and a
full Node/npm/yarn toolchain with network access (`npx` fetches `hygen` on first use).
Wired into CI only on push to `main` — see `.github/workflows/ci.yml`'s `p7-crown` job —
not on every PR, to keep PR feedback fast.

Run it directly:

```sh
git submodule update --init vendor/hygen-create
python3 scripts/gall_p7_crown.py \
  --root . \
  --receipt p7-crown-receipt.json
```

Run the unit binding:

```sh
python3 -m unittest discover -s tests -p 'test_p7_crown.py' -v
```

If any prerequisite (submodule, `ggen` binary, node/npx/yarn) is missing,
`test_p7_crown.py` skips cleanly rather than failing.
