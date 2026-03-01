"""
CLI entry point: argument parser and main().

Orchestrates the SubModule.xml and project.mbproj validation passes
for a single module, then delegates output to the output module.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .backends import is_lxml_available
from .mbproj import validate_mbproj
from .models import ValidationResult
from .output import emit_github_annotations, print_human
from .submodule import validate_module
from .xsd_resolver import DirectoryXsdResolver, XsltPatchedXsdResolver

_XSLT_PATH = Path(__file__).parent.parent / "XmlSchemas" / "expanded-api.xslt"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_module_xml",
        description=(
            "Validate Bannerlord module XML files against game XSD schemas.\n"
            "Supports both SubModule.xml and project.mbproj declarations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
XSD schemas
-----------
  The game ships XSD files in <GameDir>/XmlSchemas/. Copy that directory into
  your repo (e.g. XmlSchemas/v1.3/) and point --xsd-dir at it.

Examples
--------
  # Validate SubModule.xml only
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/v1.3

  # Validate SubModule.xml + ModuleData/project.mbproj
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/v1.3 --mbproj

  # Allow expanded equipment API attributes (siege/battle/pool)
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/v1.3 --bannerlord-xml-expanded-api
        """,
    )

    parser.add_argument(
        "--module", "-m",
        required=True,
        metavar="MODULE_DIR",
        help="Module directory (must contain SubModule.xml).",
    )
    parser.add_argument(
        "--mbproj",
        action="store_true",
        help=(
            "Also validate ModuleData/project.mbproj. "
            "Errors if the file does not exist."
        ),
    )
    parser.add_argument(
        "--xsd-dir", "-x",
        required=True,
        metavar="XSD_DIR",
        help="Directory containing the Bannerlord XSD schema files.",
    )
    parser.add_argument(
        "--game-type", "-g",
        default=None,
        metavar="GAME_TYPE",
        help=(
            "Only validate SubModule.xml nodes whose <IncludedGameTypes> contains "
            "this value (e.g. Campaign). Has no effect on project.mbproj entries."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat XSD warnings as errors (exit 1 on warnings).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit results as JSON to stdout.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show passing and skipped files in addition to failures.",
    )
    parser.add_argument(
        "--github-annotations",
        action="store_true",
        dest="github_annotations",
        help=(
            "Emit GitHub Actions ::error/::warning commands for inline PR annotations. "
            "Automatically set by the composite action."
        ),
    )
    parser.add_argument(
        "--bannerlord-xml-expanded-api",
        action="store_true",
        dest="expanded_api",
        help=(
            "Extend the XSD schemas at validation time to allow the expanded "
            "equipment API attributes (siege, battle, pool on EquipmentRoster "
            "and EquipmentSet) that Bannerlord supports but omits from the "
            "shipped XSD files.  Works with any --xsd-dir version; no "
            "hand-edited schema copies are needed.  Requires lxml."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    xsd_dir = Path(args.xsd_dir).resolve()
    if not xsd_dir.is_dir():
        print(f"ERROR: XSD directory not found: {xsd_dir}", file=sys.stderr)
        return 2

    if not is_lxml_available:
        print(
            "WARNING: lxml is not installed — schema validation disabled.\n"
            "         pip install lxml\n",
            file=sys.stderr,
        )

    module_dir = Path(args.module).resolve()
    module_id = module_dir.name

    base_resolver = DirectoryXsdResolver(xsd_dir)
    if args.expanded_api:
        try:
            resolver = XsltPatchedXsdResolver(base_resolver, _XSLT_PATH)
        except (ImportError, FileNotFoundError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        resolver = base_resolver

    try:
        results = validate_module(module_dir, resolver, args.game_type)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.mbproj:
        try:
            results.extend(validate_mbproj(module_dir / "ModuleData" / "project.mbproj", resolver))
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    all_results: dict[str, list[ValidationResult]] = {module_id: results}

    if args.github_annotations:
        emit_github_annotations(all_results, strict=args.strict)

    if args.json_output:
        print(
            json.dumps(
                {mid: [r.as_dict() for r in rs] for mid, rs in all_results.items()},
                indent=2,
            )
        )
    else:
        print_human(all_results, verbose=args.verbose, strict=args.strict, base=Path.cwd())

    has_errors = any(
        r.errors or (args.strict and r.warnings)
        for rs in all_results.values()
        for r in rs
        if not r.skipped
    )
    return 1 if has_errors else 0
