# ggen-create

Create deterministic ggen manufacturing packages from existing working examples.

## Hygen-create parity contract

The first Gall checkpoint is the canonical `hygen-create` greeter example, preserved byte-for-byte from `ronp001/hygen-create@124fac27df0ddbc498b841ba3e05997ed10e4c39` (tree `bf088a9e2ab533cd9ba035ecddb0c31f30e292bd`). The ggen-create documentation uses the same files, capture lifecycle, case-family expectations, variation, executable behavior, and revision law.

```text
hygen-create: exemplar -> Hygen generator -> generated project
ggen-create:  exemplar -> ggen package    -> generated project
```

The command correspondence is intentionally direct:

| Hygen reference | ggen-create contract |
| --- | --- |
| `hygen-create start greeter` | `ggen-create start greeter` |
| `hygen-create add package.json dist/hello.js` | `ggen-create add package.json dist/hello.js` |
| `hygen-create usename Hello` | `ggen-create usename Hello` |
| `hygen-create status` | `ggen-create status` |
| `hygen-create generate` | `ggen-create generate` |
| `hygen greeter new --name Hola` | `ggen greeter new --name Hola` |

The admitted variation must create `dist/hola.js`, update the package script, and make `npm run hola` print `Hola!`.

Run the local crown:

```sh
python3 scripts/gall_hygen_parity.py --root . --receipt gall-hygen-parity-receipt.json
python3 -m unittest discover -s tests -p 'test_parity_*.py' -v
```

See [the complete parity guide](docs/hygen-create-parity.md), [CI evidence architecture](docs/ci.md), [product requirements](product/PRD.md), and [architecture requirements](architecture/ARD.md).

## Standing

```text
reference identity and fixture bytes: ALIVE
case-family unit contract:            ALIVE
example reconstruction and variation: ALIVE when the Gall verifier succeeds
documentation-to-example closure:      ALIVE when the Gall verifier succeeds
ggen-create product runtime on main:   UNKNOWN
real ggen package manufacture:          UNKNOWN
```

A documented contract is not promoted into runtime implementation evidence. The purpose of this layer is to ensure that future product code cannot redefine the example or documentation while still claiming Hygen parity.
