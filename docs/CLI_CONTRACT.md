# CLI Contract

## Product split

```text
ggen-create  creates admitted factories
ggen         operates admitted factories
```

No `ggen-create construct-target` command is permitted.

## Command shape

```text
ggen-create <noun> <verb> [options]
```

## Capture

```bash
ggen-create capture init <name> --root <path>
ggen-create capture include <path>...
ggen-create capture exclude <path>...
ggen-create capture status
ggen-create capture freeze
```

### `capture init`

Creates a candidate capture manifest.

Does not admit the root until identity and boundary checks pass.

### `capture include`

Adds explicit paths under the fenced root.

Refuses escapes and unsupported path types according to policy.

### `capture freeze`

Content-addresses the observation and refuses later drift until a new revision is opened.

## Parameters

```bash
ggen-create parameter seed <id> --value <exemplar>
ggen-create parameter inspect <id>
ggen-create parameter admit <id>
ggen-create parameter refuse <id> --reason <code>
```

A seed is a hypothesis, not authority.

## Inference

```bash
ggen-create infer lexical
ggen-create infer structural
ggen-create infer variations
ggen-create infer ontology
ggen-create infer verification
```

All inference produces candidate graphs.

## Inspection

```bash
ggen-create inspect correspondences
ggen-create inspect collisions
ggen-create inspect unsupported
ggen-create inspect package
ggen-create inspect --format json
```

Inspection never writes target artifacts.

## Admission

```bash
ggen-create admit observations
ggen-create admit correspondences
ggen-create admit package
ggen-create admit skills
ggen-create admit agents
```

Every admission command emits a decision object.

## Package

```bash
ggen-create package build --output <dir>
ggen-create package verify
ggen-create package identity
```

`package build` emits inputs for the separate `ggen` CLI.

## Parity

```bash
ggen-create parity reference pin
ggen-create parity capture
ggen-create parity transform
ggen-create parity reconstruct
ggen-create parity vary --set name=Hola
ggen-create parity revision
ggen-create parity crown
```

## Skills and agents

```bash
ggen-create skills inspect
ggen-create skills admit
ggen-create skills project --target claude

ggen-create agents inspect
ggen-create agents admit
ggen-create agents graph
```

These commands operate on create-time capability graphs. They do not execute target manufacture.

## Verification

```bash
ggen-create verify reconstruct
ggen-create verify held-out <fixture>
ggen-create verify behavior -- <command>...
ggen-create verify replay <receipt>
```

Commands after `--` become BRCE intents. They are not executed by the planning agent.

## Receipts

```bash
ggen-create receipt show <id>
ggen-create receipt verify <path>
ggen-create receipt graph <id>
```

## Output contract

Machine-readable output must include:

```json
{
  "state": "ALIVE|PARTIAL_ALIVE|UNKNOWN|BLOCKED|BUILD_BROKEN|UNSUPPORTED|REFUSED",
  "subject": {},
  "observed": [],
  "admitted": [],
  "executed": [],
  "verified": [],
  "inferred": [],
  "refused": [],
  "unsupported": [],
  "receipts": []
}
```

## Exit policy

Suggested initial policy:

| Result | Exit |
|---|---:|
| requested checkpoint ALIVE | 0 |
| valid inspection with candidates | 0 |
| typed refusal | 2 |
| unsupported capability | 3 |
| blocked dependency/toolchain | 4 |
| build or verifier failure | 5 |
| internal invariant failure | 70 |

Exact codes become authoritative only after implementation and executable tests.
