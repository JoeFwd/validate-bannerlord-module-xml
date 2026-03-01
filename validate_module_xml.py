#!/usr/bin/env python3
"""
Bannerlord ModuleData XML Validator

Validates a Bannerlord module's XML files against the game's XSD schemas.
Supports two declaration sources:

  SubModule.xml  — <XmlNode><XmlName id="..." path="..."/></XmlNode>
                   Path is relative to <ModuleDir>/ModuleData/.
                   Supports directory expansion (all *.xml inside) and game-type filtering.

  project.mbproj — <file id="..." name="..." type="..."/>
                   Path (name) is relative to the module root (parent of the mbproj's dir).
                   No directory expansion; no game-type filtering.

Both validators share the same XSD lookup rule:
  <xsd_dir>/<id>.xsd

Usage:
  # Validate SubModule.xml + auto-detect ModuleData/project.mbproj
  python validate_module_xml.py --module ../DellarteDellaGuerraMap --xsd-dir XmlSchemas/v1.3

  # Non-standard mbproj location (e.g. RBMXML/)
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraRBM \\
      --mbproj ../DellarteDellaGuerraRBM/RBMXML/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # mbproj only, no SubModule.xml needed
  python validate_module_xml.py --mbproj path/to/project.mbproj --xsd-dir XmlSchemas/v1.3

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
