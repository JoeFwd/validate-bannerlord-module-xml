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
  python tools/validate_module_xml.py --module ../DellarteDellaGuerraMap --xsd-dir XmlSchemas/v1.3

  # Non-standard mbproj location (e.g. RBMXML/)
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraRBM \\
      --mbproj ../DellarteDellaGuerraRBM/RBMXML/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # mbproj only, no SubModule.xml needed
  python tools/validate_module_xml.py --mbproj path/to/project.mbproj --xsd-dir XmlSchemas/v1.3

  # GitHub Actions annotations (used by the composite action)
  python tools/validate_module_xml.py --module . --xsd-dir XmlSchemas/v1.3 --github-annotations

Exit codes:
  0 — all files valid (or no declarations found)
  1 — one or more files failed validation
  2 — bad arguments / missing required files
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
        return not any(i.severity == "error" for i in self.issues) and not self.skipped

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
# Validation backends  (lxml for real XSD validation, stdlib fallback)
# ---------------------------------------------------------------------------


def _validate_lxml(xml_path: Path, xsd_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    try:
        with xsd_path.open("rb") as fh:
            schema = lxml_etree.XMLSchema(lxml_etree.parse(fh))
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
# Shared validation core
# ---------------------------------------------------------------------------


def _validate_file_refs(
    xml_id: str,
    declared_path: str,
    xml_files: list[Path],
    xsd_dir: Path,
    expected_xml_path: Optional[Path] = None,
) -> list[ValidationResult]:
    """
    Validate a resolved list of XML files against a single XSD schema.

    This is the DRY core shared by both the SubModule.xml and project.mbproj
    validators. Callers are responsible for resolving xml_files themselves;
    this function only handles the XSD lookup and per-file validation loop.

    Args:
        xml_id:           Schema ID — used as the XSD filename stem.
        declared_path:    Original path string from the source file, used in
                          "file not found" skip messages.
        xml_files:        Resolved absolute paths to validate. Pass an empty
                          list when the declared file(s) could not be found.
        xsd_dir:          Directory that contains the XSD files.
        expected_xml_path: Absolute path shown in the skip result when
                          xml_files is empty. Falls back to declared_path.
    """
    xsd_path = xsd_dir / f"{xml_id}.xsd"

    if not xml_files:
        display = str(expected_xml_path) if expected_xml_path else declared_path
        return [
            ValidationResult(
                xml_path=display,
                xsd_id=xml_id,
                xsd_path=str(xsd_path),
                skipped=True,
                skip_reason=f"XML file not found for path '{declared_path}'",
            )
        ]

    results: list[ValidationResult] = []
    for xml_path in xml_files:
        result = ValidationResult(
            xml_path=str(xml_path),
            xsd_id=xml_id,
            xsd_path=str(xsd_path),
        )
        if not xsd_path.is_file():
            result.skipped = True
            result.skip_reason = f"XSD schema not found: {xsd_path.name}"
        else:
            result.issues = _validate(xml_path, xsd_path)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# SubModule.xml validator
# ---------------------------------------------------------------------------


@dataclass
class _SubModuleEntry:
    xml_id: str
    path: str
    game_types: list[str] = field(default_factory=list)  # empty = all game types


def _parse_submodule(submodule_path: Path) -> list[_SubModuleEntry]:
    """Return all <XmlNode> declarations from a SubModule.xml."""
    try:
        tree = ET.parse(submodule_path)
    except ET.ParseError as exc:
        raise ValueError(f"Cannot parse {submodule_path}: {exc}") from exc

    entries: list[_SubModuleEntry] = []
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
        entries.append(_SubModuleEntry(xml_id=xml_id, path=path, game_types=game_types))

    return entries


def _resolve_submodule_files(module_dir: Path, path_value: str) -> list[Path]:
    """
    Resolve a SubModule.xml XmlName path to one or more XML file paths.

    Mirrors MBObjectManager.GetMergedXmlForManaged resolution order:
      1. <ModuleData>/<path>.xml     — single file
      2. <ModuleData>/<path>/        — directory, collect all *.xml inside
    """
    module_data = module_dir / "ModuleData"
    stem = path_value.removesuffix(".xml")

    candidate = module_data / (stem + ".xml")
    if candidate.is_file():
        return [candidate]

    candidate_dir = module_data / stem
    if candidate_dir.is_dir():
        files = sorted(candidate_dir.glob("*.xml"))
        if files:
            return files

    return []


def validate_module(
    module_dir: Path,
    xsd_dir: Path,
    game_type_filter: Optional[str] = None,
) -> list[ValidationResult]:
    """
    Validate all XML files declared in a module's SubModule.xml.

    Raises FileNotFoundError if SubModule.xml does not exist.
    """
    submodule_path = module_dir / "SubModule.xml"
    if not submodule_path.is_file():
        raise FileNotFoundError(f"SubModule.xml not found: {submodule_path}")

    results: list[ValidationResult] = []

    for entry in _parse_submodule(submodule_path):
        if (
            game_type_filter
            and entry.game_types
            and game_type_filter not in entry.game_types
        ):
            continue

        xml_files = _resolve_submodule_files(module_dir, entry.path)
        expected = module_dir / "ModuleData" / entry.path

        results.extend(
            _validate_file_refs(entry.xml_id, entry.path, xml_files, xsd_dir, expected)
        )

    return results


# ---------------------------------------------------------------------------
# project.mbproj validator
# ---------------------------------------------------------------------------


@dataclass
class _MbProjEntry:
    xml_id: str   # <file id="...">  — XSD filename stem
    name: str     # <file name="..."> — path relative to the module root


def _parse_mbproj(mbproj_path: Path) -> list[_MbProjEntry]:
    """
    Return all <file> declarations from a project.mbproj.

    Multiple entries may share the same id (e.g. soln_decal_textures) — each
    points to a distinct XML file and must be validated individually.
    """
    try:
        tree = ET.parse(mbproj_path)
    except ET.ParseError as exc:
        raise ValueError(f"Cannot parse {mbproj_path}: {exc}") from exc

    entries: list[_MbProjEntry] = []
    for file_el in tree.getroot().findall("file"):
        xml_id = (file_el.get("id") or "").strip()
        name = (file_el.get("name") or "").strip()
        if not xml_id or not name:
            continue
        entries.append(_MbProjEntry(xml_id=xml_id, name=name))

    return entries


def validate_mbproj(
    mbproj_path: Path,
    xsd_dir: Path,
) -> list[ValidationResult]:
    """
    Validate all XML files declared in a project.mbproj.

    Path resolution: <file name="..."> is relative to the module root, which
    is the parent directory of the directory that contains the .mbproj file.

      project.mbproj at:  <ModuleRoot>/ModuleData/project.mbproj
      module root:        <ModuleRoot>/
      name="ModuleData/skins.xml"  →  <ModuleRoot>/ModuleData/skins.xml

    This also covers non-standard locations (e.g. RBMXML/project.mbproj):
      module root = <ModuleRoot>/
      name="RBMXML/combat.xml"     →  <ModuleRoot>/RBMXML/combat.xml

    Raises FileNotFoundError if the .mbproj file does not exist.
    """
    if not mbproj_path.is_file():
        raise FileNotFoundError(f"project.mbproj not found: {mbproj_path}")

    module_root = mbproj_path.parent.parent
    results: list[ValidationResult] = []

    for entry in _parse_mbproj(mbproj_path):
        xml_path = module_root / entry.name
        xml_files = [xml_path] if xml_path.is_file() else []

        results.extend(
            _validate_file_refs(entry.xml_id, entry.name, xml_files, xsd_dir, xml_path)
        )

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
                cmd = "error" if (issue.severity == "error" or strict) else "warning"
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
                print(f"::{cmd} file={file_path}{line_part},title={title}::{issue.message}")


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
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraMap \\
      --xsd-dir XmlSchemas/v1.3

  # Non-standard mbproj location (e.g. RBMXML/ instead of ModuleData/)
  python tools/validate_module_xml.py \\
      --module ../DellarteDellaGuerraRBM \\
      --mbproj ../DellarteDellaGuerraRBM/RBMXML/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # mbproj only, no SubModule.xml
  python tools/validate_module_xml.py \\
      --mbproj ../SomeModule/ModuleData/project.mbproj \\
      --xsd-dir XmlSchemas/v1.3

  # Multiple modules, Campaign-only, JSON report
  python tools/validate_module_xml.py \\
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

    if not _LXML:
        print(
            "WARNING: lxml is not installed — schema validation disabled.\n"
            "         pip install lxml\n",
            file=sys.stderr,
        )

    # all_results is keyed by module name; results from SubModule.xml and any
    # project.mbproj for the same module are merged under the same key.
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

        # Auto-detect project.mbproj at the conventional location
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
        # Derive module ID from the module root (parent of the mbproj's directory)
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


if __name__ == "__main__":
    sys.exit(main())
