# Bannerlord Module XML Validator

A Python tool and reusable GitHub Action that validates Mount & Blade II Bannerlord module XML files against the game's official XSD schemas.

It mirrors the validation logic of `TaleWorlds.ObjectSystem.MBObjectManager.LoadXmlWithValidation` — catching schema violations before they reach the game engine.

## How it works

1. Reads `SubModule.xml` to discover every `<XmlNode>` declaration.
2. Resolves each `<XmlName path="...">` to one or more XML files under `ModuleData/` (single file or all `*.xml` in a directory).
3. Looks up the matching XSD schema by the `<XmlName id="...">` value from the bundled schema set for the target Bannerlord version.
4. Validates each file against its schema and reports every violation with file path and line number.
5. Optionally repeats steps 1–4 for `ModuleData/project.mbproj`.

Bundled schema sets:

| Version | Schema count |
|---------|-------------|
| v1.2    | 29 XSD files |
| 1.3    | 49 XSD files |

---

## Local usage

**Requirements:** Python 3.11+, `lxml`

```bash
pip install lxml
```

Run the validator as a module from the repository root:

```bash
python -m validator --module <MODULE_DIR> --bannerlord-version <VERSION> [OPTIONS]
```

### Required arguments

| Argument | Description |
|---|---|
| `--module MODULE_DIR` / `-m` | Path to the module directory. Must contain `SubModule.xml`. |
| `--bannerlord-version VERSION` / `-x` | Target game version. Accepted values: `1.2`, `1.3`. |

### Optional arguments

| Argument | Description |
|---|---|
| `--mbproj` | Also validate `ModuleData/project.mbproj`. Errors if the file does not exist. |
| `--bannerlord-xml-expanded-api` | Extend schemas at validation time to allow the expanded equipment API attributes (`siege`, `battle`, `pool` on `EquipmentRoster`/`EquipmentSet`) that the game supports but omits from its shipped XSD files. Requires `lxml`. |
| `--verbose` / `-v` | Show passing and skipped files in addition to failures. |
| `--json` | Emit results as JSON to stdout instead of human-readable output. |

### Examples

```bash
# Validate a module against 1.3 schemas
python -m validator \
    --module ../DellarteDellaGuerraMap \
    --bannerlord-version 1.3

# Validate SubModule.xml + project.mbproj
python -m validator \
    --module ../DellarteDellaGuerraMap \
    --bannerlord-version 1.3 --mbproj

# Allow expanded equipment API attributes (siege/battle/pool)
python -m validator \
    --module ../DellarteDellaGuerraMap \
    --bannerlord-version 1.3 --bannerlord-xml-expanded-api

# Show all files including passing ones
python -m validator \
    --module ../DellarteDellaGuerraMap \
    --bannerlord-version 1.3 --verbose

# Emit JSON for tooling integration
python -m validator \
    --module ../DellarteDellaGuerraMap \
    --bannerlord-version 1.3 --json
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All validated files passed. |
| `1` | One or more schema violations found. |
| `2` | Fatal error (missing SubModule.xml, unsupported version, bad mbproj, etc.). |

## GitHub Action

The action is a composite action that sets up Python, installs `lxml`, and runs the validator so that every schema violation appears in the step log.

### Adding the action to a workflow

Add a step referencing this action in your existing workflow file (`.github/workflows/*.yml`):

```yaml
- name: Validate module XML
  uses: JoeFwd/bannerlord-xml-validator@<version>
  with:
    module-path: MyModule          # relative to the repo root
    bannerlord-version: '1.3'
```

### Full example workflow

```yaml
name: Validate XML

on:
  pull_request:
  push:
    branches: [main, develop]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate module XML
        uses: JoeFwd/bannerlord-xml-validator@<version>
        with:
          module-path: MyModule
          bannerlord-version: '1.3'
```

### Action inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `module-path` | yes | — | Path to the module directory (must contain `SubModule.xml`). Relative to the repository root (`$GITHUB_WORKSPACE`). |
| `bannerlord-version` | no | `1.3` | Target Bannerlord version. Accepts `1.2`, `1.3` |
| `validate-mbproj` | no | `false` | Also validate `ModuleData/project.mbproj`. |
| `bannerlord-xml-expanded-api` | no | `false` | Extend schemas to allow the expanded equipment API attributes (`siege`, `battle`, `pool` on `EquipmentRoster`/`EquipmentSet`). No hand-edited schema copies needed. |
| `verbose` | no | `false` | Show passing and skipped files in the step log. |

### Action outputs

| Output | Description |
|---|---|
| `result` | `"pass"` if all validated files are valid, `"fail"` otherwise. |

### Checking the result in subsequent steps

```yaml
- name: Validate module XML
  id: xml-check
  uses: JoeFwd/bannerlord-xml-validator@<version>
  with:
    module-path: MyModule
    bannerlord-version: '1.3'

- name: Report outcome
  if: always()
  run: echo "Validation result: ${{ steps.xml-check.outputs.result }}"
```

### Validating multiple modules

```yaml
strategy:
  matrix:
    module: [ModuleA, ModuleB, ModuleC]
steps:
  - uses: actions/checkout@v4

  - name: Validate ${{ matrix.module }}
    uses: JoeFwd/bannerlord-xml-validator@<version>
    with:
      module-path: ${{ matrix.module }}
      bannerlord-version: '1.3'
```
