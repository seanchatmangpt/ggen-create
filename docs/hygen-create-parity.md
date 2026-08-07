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
