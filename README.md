# bannerlord-xml-validator

A GitHub composite action that validates Bannerlord module `ModuleData` XML files
against the game's XSD schemas.

Mirrors the two-pass validation in
`TaleWorlds.ObjectSystem.MBObjectManager.LoadXmlWithValidation` and emits inline
pull-request annotations for every schema violation.

## Bundled schemas

| Directory | Game version | XSD count |
|-----------|-------------|-----------|
| `XmlSchemas/v1.2/` | Bannerlord v1.2 | 29 |
| `XmlSchemas/v1.3/` | Bannerlord v1.3 | 49 |

Update the relevant subdirectory when a new game version adds or changes schemas.

## Usage

```yaml
- name: Validate XML
  uses: <your-org>/bannerlord-xml-validator@v1
  with:
    bannerlord-version: 'v1.3'
    module-paths: |
      ${{ github.workspace }}/DellarteDellaGuerraMap
      ${{ github.workspace }}/DellarteDellaGuerra
```

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `module-paths` | yes | — | Newline-separated module directory paths (each must contain `SubModule.xml`) |
| `bannerlord-version` | no | `v1.3` | Target game version. Accepts `v1.2`, `v1.3`, `1.3`, `v1.3.8` — only major.minor matters |
| `game-type` | no | *(all)* | Only validate XML nodes included for this game type (e.g. `Campaign`) |
| `strict` | no | `false` | Treat XSD warnings as errors |
| `verbose` | no | `false` | Show passing and skipped files in the log |

### Outputs

| Output | Description |
|--------|-------------|
| `result` | `"pass"` or `"fail"` |

## Full workflow example

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Checkout DellarteDellaGuerraMap
        uses: actions/checkout@v4
        with:
          repository: ${{ github.repository_owner }}/DellarteDellaGuerraMap
          path: DellarteDellaGuerraMap

      - name: Validate XML
        uses: <your-org>/bannerlord-xml-validator@v1
        with:
          bannerlord-version: 'v1.3'
          module-paths: |
            ${{ github.workspace }}/DellarteDellaGuerraMap
          game-type: Campaign
          verbose: 'true'
```

## Local usage

```bash
pip install lxml

# v1.3 schemas
python validate_module_xml.py \
  --module /path/to/DellarteDellaGuerraMap \
  --xsd-dir XmlSchemas/v1.3 \
  --verbose

# v1.2 schemas
python validate_module_xml.py \
  --module /path/to/DellarteDellaGuerraMap \
  --xsd-dir XmlSchemas/v1.2 \
  --verbose
```
