"""
CLI entry point: argument parser and main().

Orchestrates the SubModule.xml and project.mbproj validation passes,
merges results by module name, and delegates output to the output module.
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
  # Module with SubModule.xml (mbproj auto-detected if present)
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/v1.3

  # Non-standard mbproj location (e.g. RBMXML/ instead of ModuleData/)
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraRBM \\
      --mbproj ../DellarteDellaGuerraRBM/RBMXML/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # mbproj only, no SubModule.xml
  python validate_module_xml.py \\
      --mbproj ../SomeModule/ModuleData/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # Multiple modules, Campaign-only, JSON report
  python validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --module ../DellarteDellaGuerra \\
      --xsd-dir XmlSchemas/v1.3 --game-type Campaign --json
        """,
    )

    parser.add_argument(
        "--module", "-m",
        dest="modules",
        action="append",
        default=[],
        metavar="MODULE_DIR",
        help=(
            "Module directory (must contain SubModule.xml). "
            "Also auto-validates ModuleData/project.mbproj if present. "
            "Repeat for multiple modules."
        ),
    )
    parser.add_argument(
        "--mbproj",
        dest="mbprojs",
        action="append",
        default=[],
        metavar="MBPROJ_PATH",
        help=(
            "Path to a project.mbproj file. Use for non-standard locations "
            "(e.g. RBMXML/project.mbproj) or when there is no SubModule.xml. "
            "Repeat for multiple files. Results are merged with --module results "
            "when both share the same module root name."
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.modules and not args.mbprojs:
        parser.error("at least one of --module or --mbproj is required")

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

    # Results keyed by module name; SubModule.xml and mbproj results for the
    # same module are merged under the same key.
    all_results: dict[str, list[ValidationResult]] = {}
    repo_root = Path.cwd()

    # --- SubModule.xml pass (also auto-detects ModuleData/project.mbproj) ---
    for module_path in args.modules:
        module_dir = Path(module_path).resolve()
        module_id = module_dir.name

        try:
            results = validate_module(module_dir, xsd_dir, args.game_type)
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        default_mbproj = module_dir / "ModuleData" / "project.mbproj"
        if default_mbproj.is_file():
            try:
                results.extend(validate_mbproj(default_mbproj, xsd_dir))
            except (FileNotFoundError, ValueError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2

        all_results.setdefault(module_id, []).extend(results)

    # --- Explicit --mbproj pass (non-standard locations) ---
    for mbproj_str in args.mbprojs:
        mbproj_path = Path(mbproj_str).resolve()
        module_id = mbproj_path.parent.parent.name

        try:
            results = validate_mbproj(mbproj_path, xsd_dir)
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        all_results.setdefault(module_id, []).extend(results)

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
        print_human(all_results, verbose=args.verbose, strict=args.strict, base=repo_root)

    has_errors = any(
        r.errors or (args.strict and r.warnings)
        for rs in all_results.values()
        for r in rs
        if not r.skipped
    )
    return 1 if has_errors else 0
