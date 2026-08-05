# CLI Contract

## Product split

```text
ggen-create  creates admitted factories
ggen         operates admitted factories
```

No `ggen-create construct-target` command is permitted.

The parity verifier may invoke the public `ggen` process in isolated staging. That is verification of a manufactured factory, not an embedded construction engine.

## Phase 1: implemented parity surface

### Original-compatible commands

```bash
ggen-create start <generator-name> [--root <path>]
ggen-create rename <generator-name>
ggen-create add [-r] <file-or-dir>...
ggen-create remove <file>...
ggen-create rm <file>...
ggen-create usename <seed>
ggen-create setopt --gen-parent-dir
ggen-create setopt --no-parent-dir
ggen-create status [-v] [file...]
ggen-create s [-v] [file...]
ggen-create generate [--output <dir>] [--force]
ggen-create g [--output <dir>] [--force]
ggen-create abort
ggen-create verify <options>
ggen-create compare <left-tree> <right-tree>
```

Global options:

```bash
-p, --project <capture-file>   # default: ggen-create.json
--json                         # machine-readable output
```

The capture state deliberately retains the original six-field `hygen-create.json` shape. Its filesystem location defines the capture root.

### Native aliases

The same deterministic skills are available under create-side nouns:

```bash
ggen-create capture init <name> [--root <path>]
ggen-create capture include [-r] <path>...
ggen-create capture remove <path>...
ggen-create capture abort

ggen-create parameter seed <value>

ggen-create package build [--output <dir>] [--force]

ggen-create parity verify <options>
ggen-create parity compare <left-tree> <right-tree>
```

These are aliases, not a second implementation.

## Capture behavior

### `start`

Creates `ggen-create.json` and automatically admits that session file, matching the original iterative-generator workflow.

Refuses:

```text
CAPTURE_ROOT_MISSING_REFUSED
SESSION_IN_PROGRESS_REFUSED
```

### `add`

Admits UTF-8 regular files beneath the session root.

A directory contributes immediate regular-file children. `--recursive` additionally traverses descendant directories.

Refuses:

```text
PATH_MISSING_REFUSED
PATH_OUTSIDE_CAPTURE_ROOT_REFUSED
SYMLINK_REFUSED
BINARY_FILE_REFUSED
NON_UTF8_FILE_REFUSED
```

### `usename`

Sets the single parity parameter seed. Multiple parameters remain Phase 2.

### `status`

Mechanically reports:

- admitted source path;
- parameterized target path;
- path occurrences;
- content occurrences;
- transform selected for each occurrence;
- total replacement count;
- parent-directory mode.

Inspection does not emit target artifacts.

## Package behavior

```bash
ggen-create generate --output <package-root>
```

Emits:

```text
<package-root>/<generator>/
├── ggen.toml
├── ontology.ttl
├── templates/*.tmpl
├── ggen-create-package.json
└── receipt.json
```

An identical rerun returns `changed = false`.

A changed package archives the previous current package as `<generator>.1`, `<generator>.2`, and so on, then installs the new package at `<generator>`.

## Parity verification

```bash
ggen-create verify \
  --output <verification-root> \
  --ggen-bin <path> \
  --set <variation-value> \
  [--sync-arg <arg>]... \
  [--check-command <shell-command>] \
  [--stdout-contains <text>] \
  [--reference-dir <original-output>] \
  [--reference-id <pinned-toolchain>] \
  [--force]
```

Default ggen arguments are:

```text
sync run
```

`--sync-arg` is repeatable and replaces that default.

Behavior commands run only inside the clean variation artifact projection. The following placeholders are admitted:

```text
{name}
{upper}
{lower}
{capitalized}
{pascal}
{camel}
{snake}
{upper_snake}
{kebab}
{title}
```

The verifier writes `parity-report.json` and calculates P0–P7 standing.

P7 may be `ALIVE` only when both `--reference-dir` and `--reference-id` are supplied and byte-exact comparison succeeds.

## Exit policy

| Result | Exit |
|---|---:|
| successful mutation, inspection, package build, or checkpoint | 0 |
| tree comparison differs | 1 |
| typed refusal or failed verifier | 2 |
| argparse usage error | 2 |

Later native rails may reserve additional exit classes, but Phase 1 does not fabricate distinctions it has not implemented.

## Phase 2+ reserved surface

The following design remains reserved until its own executable checkpoint exists:

```bash
ggen-create infer lexical
ggen-create infer structural
ggen-create infer variations
ggen-create infer ontology
ggen-create infer verification

ggen-create admit observations
ggen-create admit correspondences
ggen-create admit package
ggen-create admit skills
ggen-create admit agents

ggen-create skills inspect
ggen-create skills admit
ggen-create skills project --target claude

ggen-create agents inspect
ggen-create agents admit
ggen-create agents graph
```

Reserved commands must not be registered as stubs. Unsupported future capability remains absent from the executable surface.
