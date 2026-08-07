# Greeter parity fixture

This is the first required ALIVE fixture.

## Exemplar

```text
hello/
├── package.json
└── dist/
    └── hello.js
```

`package.json`:

```json
{
  "name": "hello",
  "version": "1.0.0",
  "scripts": {
    "hello": "node dist/hello.js"
  }
}
```

`dist/hello.js`:

```javascript
console.log("Hello!")
```

## Capture

Illustrative capture object:

```toml
version = "0.1"

[subject]
name = "greeter"
root = "./hello"
tree_hash = "blake3:pending"

[policy]
symlinks = "refuse"
binary_files = "exclude"
outside_root = "refuse"

[[include]]
path = "package.json"
standing = "candidate"

[[include]]
path = "dist/hello.js"
standing = "candidate"

[[parameter_hypotheses]]
id = "name"
seed = "Hello"
standing = "candidate"
```

## Required parity consequences

### Reconstruction

```text
name = Hello
```

must reconstruct the original tree.

### Variation

```text
name = Hola
```

must produce:

```text
package name: hola
script name:  hola
script path:  dist/hola.js
stdout:       Hola!
```

## Required comparison

Run both rails from pinned toolchains:

```text
hygen-create → Hygen
ggen-create  → ggen
```

Compare:

- output paths;
- output bytes;
- executable behavior;
- revision identity;
- replay.

## Standing

The example documentation exists, but no execution is claimed:

```text
fixture definition: ADMITTED
reference execution: UNKNOWN
ggen-create execution: UNKNOWN
parity standing: UNKNOWN
```
