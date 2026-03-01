#!/usr/bin/env python3
"""
Bannerlord ModuleData XML Validator

Validates a Bannerlord module's XML files against the game's XSD schemas.

Mirrors the validation logic from:
  TaleWorlds.ObjectSystem.MBObjectManager.LoadXmlWithValidation
  TaleWorlds.ModuleManager.ModuleHelper.GetXsdPath / GetXmlPath

Schema discovery:
  XSD:  <xsd_dir>/<XmlName id>.xsd
  XML:  <module_dir>/ModuleData/<XmlName path>[.xml]
        or all *.xml files if <XmlName path> resolves to a directory

Usage:
  python tools/validate_module_xml.py \\
    --module /path/to/MyModule \\
    --xsd-dir XmlSchemas/

  # Multiple modules, filter by game type
  python tools/validate_module_xml.py \\
    --module ModuleA --module ModuleB \\
    --xsd-dir XmlSchemas/ --game-type Campaign

  # GitHub Actions annotations (used by the composite action)
  python tools/validate_module_xml.py \\
    --module . --xsd-dir XmlSchemas/ --github-annotations

Exit codes:
  0 - All files valid (or no XML declarations found)
  1 - One or more files failed validation
  2 - Bad arguments / missing files
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Optional

try:
    from lxml import etree as lxml_etree

    _LXML = True
except ImportError:
    _LXML = False


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    line: int
    message: str


@dataclass
class XmlNodeDecl:
    """A single <XmlNode> declaration parsed from SubModule.xml."""

    xml_id: str  # Value of XmlName[@id], also the XSD filename stem
    path: str  # Value of XmlName[@path], relative to ModuleData/
    game_types: list[str] = field(default_factory=list)  # Empty = all game types


@dataclass
class ValidationResult:
    xml_path: str
    xsd_id: str
    xsd_path: str
    issues: list[ValidationIssue] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def errors(self) -> list[str]:
        return [
            f"line {i.line}: {i.message}"
            for i in self.issues
            if i.severity == "error"
        ]

    @property
    def warnings(self) -> list[str]:
        return [
            f"line {i.line}: {i.message}"
            for i in self.issues
            if i.severity == "warning"
        ]

    @property
    def is_valid(self) -> bool:
        return (
            not any(i.severity == "error" for i in self.issues) and not self.skipped
        )

    def as_dict(self) -> dict:
        return {
            "xml_path": self.xml_path,
            "xsd_id": self.xsd_id,
            "xsd_path": self.xsd_path,
            "valid": self.is_valid,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# SubModule.xml parsing
# ---------------------------------------------------------------------------


def parse_submodule(submodule_path: Path) -> list[XmlNodeDecl]:
    """Return all <XmlNode> declarations from a SubModule.xml."""
    try:
        tree = ET.parse(submodule_path)
    except ET.ParseError as exc:
        raise ValueError(f"Cannot parse {submodule_path}: {exc}") from exc

    nodes: list[XmlNodeDecl] = []
    for xml_node in tree.getroot().findall(".//Xmls/XmlNode"):
        name_el = xml_node.find("XmlName")
        if name_el is None:
            continue
        xml_id = (name_el.get("id") or "").strip()
        path = (name_el.get("path") or "").strip()
        if not xml_id or not path:
            continue
        game_types = [
            gt.get("value", "")
            for gt in xml_node.findall(".//IncludedGameTypes/GameType")
        ]
        nodes.append(XmlNodeDecl(xml_id=xml_id, path=path, game_types=game_types))

    return nodes


# ---------------------------------------------------------------------------
# XML file resolution  (mirrors MBObjectManager.GetMergedXmlForManaged)
# ---------------------------------------------------------------------------


def resolve_xml_files(module_dir: Path, path_value: str) -> list[Path]:
    """
    Resolve an XmlName path to one or more absolute XML file paths.

    The game engine tries, in order:
      1. <ModuleData>/<path>.xml  (file)
      2. <ModuleData>/<path>/     (directory) → collect all *.xml inside

    The path may or may not already carry the .xml extension.
    """
    module_data = module_dir / "ModuleData"
    stem = path_value.removesuffix(".xml")

    # 1. Single file
    candidate = module_data / (stem + ".xml")
    if candidate.is_file():
        return [candidate]

    # 2. Directory
    candidate_dir = module_data / stem
    if candidate_dir.is_dir():
        files = sorted(candidate_dir.glob("*.xml"))
        if files:
            return files

    return []


# ---------------------------------------------------------------------------
# Validation backends
# ---------------------------------------------------------------------------


def _validate_lxml(xml_path: Path, xsd_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    try:
        with xsd_path.open("rb") as fh:
            xsd_doc = lxml_etree.parse(fh)
        schema = lxml_etree.XMLSchema(xsd_doc)
    except (lxml_etree.XMLSyntaxError, lxml_etree.XMLSchemaParseError) as exc:
        issues.append(ValidationIssue("error", 0, f"Failed to compile XSD schema: {exc}"))
        return issues

    try:
        with xml_path.open("rb") as fh:
            xml_doc = lxml_etree.parse(fh)
    except lxml_etree.XMLSyntaxError as exc:
        issues.append(ValidationIssue("error", getattr(exc, "lineno", 0) or 0, f"XML syntax error: {exc}"))
        return issues

    schema.validate(xml_doc)
    for entry in schema.error_log:
        severity = "error" if entry.level_name == "ERROR" else "warning"
        issues.append(ValidationIssue(severity, entry.line, entry.message))

    return issues


def _validate_stdlib(xml_path: Path, _xsd_path: Path) -> list[ValidationIssue]:
    """Fallback: only checks XML well-formedness (no schema validation)."""
    try:
        ET.parse(xml_path)
    except ET.ParseError as exc:
        line = exc.position[0] if exc.position else 0
        return [ValidationIssue("error", line, f"XML parse error: {exc}")]
    return [
        ValidationIssue(
            "warning",
            0,
            "XSD validation skipped — install lxml for full schema validation: pip install lxml",
        )
    ]


_validate = _validate_lxml if _LXML else _validate_stdlib


# ---------------------------------------------------------------------------
# Module validation
# ---------------------------------------------------------------------------


def validate_module(
    module_dir: Path,
    xsd_dir: Path,
    game_type_filter: Optional[str] = None,
) -> list[ValidationResult]:
    """Validate all XML files declared in a module's SubModule.xml."""
    submodule_path = module_dir / "SubModule.xml"
    if not submodule_path.is_file():
        raise FileNotFoundError(f"SubModule.xml not found: {submodule_path}")

    nodes = parse_submodule(submodule_path)
    results: list[ValidationResult] = []

    for node in nodes:
        if (
            game_type_filter
            and node.game_types
            and game_type_filter not in node.game_types
        ):
            continue

        xsd_path = xsd_dir / f"{node.xml_id}.xsd"
        xml_files = resolve_xml_files(module_dir, node.path)

        if not xml_files:
            results.append(
                ValidationResult(
                    xml_path=str(module_dir / "ModuleData" / node.path),
                    xsd_id=node.xml_id,
                    xsd_path=str(xsd_path),
                    skipped=True,
                    skip_reason=f"XML file not found for path '{node.path}'",
                )
            )
            continue

        for xml_path in xml_files:
            result = ValidationResult(
                xml_path=str(xml_path),
                xsd_id=node.xml_id,
                xsd_path=str(xsd_path),
            )

            if not xsd_path.is_file():
                result.skipped = True
                result.skip_reason = f"XSD schema not found: {xsd_path.name}"
                results.append(result)
                continue

            result.issues = _validate(xml_path, xsd_path)
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _rel(path: str, base: Path) -> str:
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return path


def emit_github_annotations(
    all_results: dict[str, list[ValidationResult]],
    strict: bool,
) -> None:
    """
    Emit GitHub Actions workflow commands so errors appear as inline annotations
    in pull request diffs.
    https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#setting-an-error-message
    """
    workspace = os.environ.get("GITHUB_WORKSPACE", "")

    for results in all_results.values():
        for r in results:
            if r.skipped:
                continue
            for issue in r.issues:
                if issue.severity == "warning" and not strict:
                    cmd = "warning"
                elif issue.severity == "error":
                    cmd = "error"
                else:
                    # strict=True treats warnings as errors
                    cmd = "error"

                # Make path relative to GITHUB_WORKSPACE for correct annotation links
                try:
                    file_path = (
                        str(Path(r.xml_path).relative_to(workspace))
                        if workspace
                        else r.xml_path
                    )
                except ValueError:
                    file_path = r.xml_path
                file_path = file_path.replace("\\", "/")

                title = f"XSD validation {issue.severity} [{r.xsd_id}]"
                line_part = f",line={issue.line}" if issue.line else ""
                print(
                    f"::{cmd} file={file_path}{line_part},title={title}::{issue.message}"
                )


def print_human(
    all_results: dict[str, list[ValidationResult]],
    verbose: bool,
    strict: bool,
    base: Path,
) -> None:
    for module_id, results in all_results.items():
        validated = [r for r in results if not r.skipped]
        skipped = [r for r in results if r.skipped]
        failed = [r for r in validated if r.errors]
        warned = [r for r in validated if r.warnings and not r.errors]

        status = (
            f"[{module_id}]  "
            f"{len(validated)} validated, "
            f"{len(skipped)} skipped"
            + (f", {len(failed)} FAILED" if failed else "")
            + (f", {len(warned)} warned" if warned and not failed else "")
        )
        print(status)

        for r in results:
            label = _rel(r.xml_path, base)
            if r.skipped:
                if verbose:
                    print(f"  SKIP  {label}")
                    print(f"          {r.skip_reason}")
                continue

            if r.errors:
                print(f"  FAIL  {label}")
                for e in r.errors:
                    print(f"          ERROR: {e}")
                for w in r.warnings:
                    print(f"          WARN:  {w}")
            elif r.warnings:
                if verbose or strict:
                    print(f"  WARN  {label}")
                    for w in r.warnings:
                        print(f"          WARN:  {w}")
            elif verbose:
                print(f"  OK    {label}")

        if failed:
            print(f"  => {len(failed)} file(s) FAILED\n")
        else:
            print(f"  => All files passed\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_module_xml",
        description="Validate Bannerlord module XML files against game XSD schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
XSD schemas
-----------
  The game ships XSD files in <GameDir>/XmlSchemas/. Copy that directory into
  your repository (e.g. as XmlSchemas/) and point --xsd-dir at it.
  The file names match XmlName[@id] in SubModule.xml (NPCCharacters -> NPCCharacters.xsd).

Examples
--------
  # Local dev
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir "C:/Steam/steamapps/common/Mount & Blade II Bannerlord/XmlSchemas"

  # CI with bundled schemas
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/ --verbose

  # Multiple modules, Campaign only, JSON report
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --module ../DellarteDellaGuerra \\
      --xsd-dir XmlSchemas/ \\
      --game-type Campaign --json
        """,
    )

    parser.add_argument(
        "--module", "-m",
        dest="modules",
        action="append",
        required=True,
        metavar="MODULE_DIR",
        help=(
            "Path to a module directory (must contain SubModule.xml). "
            "Repeat to validate multiple modules."
        ),
    )
    parser.add_argument(
        "--xsd-dir", "-x",
        required=True,
        metavar="XSD_DIR",
        help="Path to the Bannerlord XmlSchemas directory.",
    )
    parser.add_argument(
        "--game-type", "-g",
        default=None,
        metavar="GAME_TYPE",
        help=(
            "Only validate XML nodes whose <IncludedGameTypes> contains this value "
            "(e.g. Campaign, CampaignStoryMode, CustomGame). "
            "Nodes with no <IncludedGameTypes> are always included."
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
            "Emit GitHub Actions workflow commands (::error/::warning) for inline "
            "PR annotations. Typically set automatically by the composite action."
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

    if not _LXML:
        print(
            "WARNING: lxml is not installed — schema validation disabled.\n"
            "         pip install lxml\n",
            file=sys.stderr,
        )

    all_results: dict[str, list[ValidationResult]] = {}
    repo_root = Path.cwd()

    for module_path in args.modules:
        module_dir = Path(module_path).resolve()
        module_id = module_dir.name
        try:
            results = validate_module(
                module_dir=module_dir,
                xsd_dir=xsd_dir,
                game_type_filter=args.game_type,
            )
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        all_results[module_id] = results

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


if __name__ == "__main__":
    sys.exit(main())
