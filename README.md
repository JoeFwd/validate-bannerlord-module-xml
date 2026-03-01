# bannerlord-xml-validator

A GitHub composite action that validates Bannerlord module `ModuleData` XML files
against the game's XSD schemas.

Mirrors the two-pass validation in
`TaleWorlds.ObjectSystem.MBObjectManager.LoadXmlWithValidation` and emits inline
pull-request annotations for every schema violation.

## Bundled schemas

`XmlSchemas/` contains the 49 XSD files shipped with **Bannerlord v1.3**.
Update this directory when targeting a different game version.

## Usage

```yaml
- name: Validate XML
  uses: <your-org>/bannerlord-xml-validator@v1
  with:
    module-paths: |
      ${{ github.workspace }}/DellarteDellaGuerraMap
      ${{ github.workspace }}/DellarteDellaGuerra
```

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `module-paths` | yes | — | Newline-separated list of module directory paths (each must contain `SubModule.xml`) |
| `game-type` | no | *(all)* | Only validate XML nodes included for this game type (e.g. `Campaign`) |
| `strict` | no | `false` | Treat XSD warnings as errors |
| `verbose` | no | `false` | Show passing and skipped files in the log |

### Outputs

| Output | Description |
|--------|-------------|
| `result` | `"pass"` or `"fail"` |

## Local usage

The bundled `validate_module_xml.py` can also be run locally:

```bash
pip install lxml

python validate_module_xml.py \
  --module /path/to/DellarteDellaGuerraMap \
  --xsd-dir XmlSchemas/ \
  --verbose
```

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
          module-paths: |
            ${{ github.workspace }}/DellarteDellaGuerraMap
          game-type: Campaign
          verbose: 'true'
```
