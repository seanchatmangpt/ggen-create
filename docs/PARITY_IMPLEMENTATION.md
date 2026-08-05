# Hygen-create parity implementation

## Scope

This implementation closes the deterministic create-side rail. It does not implement structural anti-unification, multiple parameters, skills, agents, or general repository synthesis.

The reference architecture is:

```text
hygen-create: exemplar → Hygen generator
Hygen:        generator + name → artifact


ggen-create: exemplar → ggen package
ggen:        package + RDF subject → artifact
```

## Module map

| Module | Responsibility |
|---|---|
| `session.py` | Original-compatible capture lifecycle and bounded path admission |
| `cases.py` | Case-family inference, occurrence discovery, Tera parameterization, concrete replay |
| `inspect.py` | Mechanical preview and correspondence report |
| `package.py` | Deterministic ggen project emission and revision archival |
| `verify.py` | Real ggen subprocess execution, artifact projection, behavior checks, reference comparison |
| `cli.py` | Original-compatible and native command surfaces |

## Original compatibility

The capture file deliberately preserves the original six fields and their order:

```json
{
  "about": "...",
  "hygen_create_version": "0.2.0",
  "name": "greeter",
  "files_and_dirs": {
    "ggen-create.json": true
  },
  "templatize_using_name": null,
  "gen_parent_dir": false
}
```

This matters because the original includes the capture file in its generated output. Preserving the shape allows the Hello→Hola reference artifact to be compared byte-for-byte.

## Admitted transformations

For a seed such as `HelloWorld`, the parity rail derives:

| Variable | Value |
|---|---|
| `upper` | `HELLOWORLD` |
| `lower` | `helloworld` |
| `capitalized` | `HelloWorld` |
| `pascal` | `HelloWorld` |
| `camel` | `helloWorld` |
| `snake` | `hello_world` |
| `upper_snake` | `HELLO_WORLD` |
| `kebab` | `hello-world` |
| `title` | `Hello World` |

Duplicate lexical values are admitted under the first transform in the original implementation's priority order.

Occurrences require either the start of the string or a non-alphanumeric preceding character, matching the original regular-expression boundary behavior.

## Generated ggen package

Each admitted source file becomes one `.tmpl` file with:

- a parameterized `to:` path;
- one SPARQL query selecting all admitted name forms;
- `for_each: entities`;
- a Tera body composed from raw static segments and explicit `row.<form>` bindings.

Static source content is wrapped in Tera raw blocks. A source containing the raw-block terminator is refused rather than silently corrupted.

## Refusals

The deterministic rail includes typed refusals for:

```text
CAPTURE_ROOT_MISSING_REFUSED
SESSION_IN_PROGRESS_REFUSED
NO_SESSION_REFUSED
SESSION_PARSE_REFUSED
SESSION_SCHEMA_REFUSED
PATH_MISSING_REFUSED
PATH_OUTSIDE_CAPTURE_ROOT_REFUSED
SYMLINK_REFUSED
BINARY_FILE_REFUSED
NON_UTF8_FILE_REFUSED
INCLUDED_PATH_MISSING_REFUSED
NO_FILES_ADMITTED_REFUSED
PARAMETER_NOT_SEEDED_REFUSED
TERA_RAW_SENTINEL_REFUSED
TEMPLATED_SOURCE_PATH_REFUSED
VERIFY_OUTPUT_EXISTS_REFUSED
GGEN_EXECUTION_REFUSED
RECONSTRUCTION_DRIFT_REFUSED
BEHAVIOR_COMMAND_REFUSED
BEHAVIOR_ASSERTION_REFUSED
REFERENCE_PARITY_DRIFT_REFUSED
IDENTICAL_REVISION_DRIFT_REFUSED
REVISION_ARCHIVE_REFUSED
```

## Revision checkpoint

Package manufacture is content-addressed at the file-set level:

1. an identical rerun returns `changed = false`;
2. a changed exemplar renames the current package to `<name>.1`, `<name>.2`, and so on;
3. the new package becomes `<name>`;
4. failure restores the archived package when possible.

The parity verifier executes this behavior in an isolated source copy so the admitted exemplar remains unchanged.

## Verification capsule

`verify` creates separate staging directories for reconstruction and variation:

```text
verification/
├── package/
├── reconstruction-run/
├── reconstruction-artifact/
├── variation-run/
├── variation-artifact/
├── revision-source/
├── revision-packages/
└── parity-report.json
```

The ggen package remains in each `*-run` directory. Only declared generated artifacts are copied into the clean `*-artifact` projection. Original-reference comparison is performed against that clean projection.

## Claim ceiling

Local tests prove deterministic create-side behavior and verifier orchestration. They do not prove the external tools.

The exact P7 crown requires one workflow execution containing all of:

```text
original hygen-create package installation
original Hygen generator execution
real ggen build
real ggen reconstruction
real ggen variation
behavioral command success
byte-exact reference comparison
parity report artifact
```
