#!/usr/bin/env python3
"""
Bannerlord ModuleData XML Validator

Validates a Bannerlord module's XML files against the game's XSD schemas.
Supports two declaration sources:

  SubModule.xml  — <XmlNode><XmlName id="..." path="..."/></XmlNode>
                   Path is relative to <ModuleDir>/ModuleData/.
                   Supports directory expansion (all *.xml inside) and game-type filtering.

  project.mbproj — <file id="..." name="..." type="..."/>  (opt-in via --mbproj)
                   Must be at ModuleData/project.mbproj inside each module directory.
                   No directory expansion; no game-type filtering.

Both validators share the same XSD lookup rule:
  <xsd_dir>/<id>.xsd

Usage:
  # Validate SubModule.xml only
  python validate_module_xml.py --module ../DellarteDellaGuerraMap --xsd-dir XmlSchemas/v1.3

  # Validate SubModule.xml + ModuleData/project.mbproj
  python validate_module_xml.py --module ../DellarteDellaGuerraMap --xsd-dir XmlSchemas/v1.3 --mbproj

  # GitHub Actions annotations (used by the composite action)
  python validate_module_xml.py --module . --xsd-dir XmlSchemas/v1.3 --github-annotations

Exit codes:
  0 — all files valid (or no declarations found)
  1 — one or more files failed validation
  2 — bad arguments / missing required files
"""

import sys

from validator.cli import main

if __name__ == "__main__":
    sys.exit(main())
