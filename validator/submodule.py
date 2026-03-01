"""
SubModule.xml validator.

Parses <XmlNode> declarations from SubModule.xml, resolves each path to one
or more XML files (single file or directory expansion), and validates them
against the matching XSD schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from .core import validate_file_refs
from .models import ValidationResult
from .xsd_resolver import XsdResolver


@dataclass
class SubModuleEntry:
    xml_id: str
    path: str
    game_types: list[str] = field(default_factory=list)  # empty = all game types


def parse_submodule(submodule_path: Path) -> list[SubModuleEntry]:
    """Return all <XmlNode> declarations from a SubModule.xml."""
    try:
        tree = ET.parse(submodule_path)
    except ET.ParseError as exc:
        raise ValueError(f"Cannot parse {submodule_path}: {exc}") from exc

    entries: list[SubModuleEntry] = []
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
        entries.append(SubModuleEntry(xml_id=xml_id, path=path, game_types=game_types))

    return entries


def resolve_submodule_files(module_dir: Path, path_value: str) -> list[Path]:
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
    resolver: XsdResolver,
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
    for entry in parse_submodule(submodule_path):
        if (
            game_type_filter
            and entry.game_types
            and game_type_filter not in entry.game_types
        ):
            continue

        xml_files = resolve_submodule_files(module_dir, entry.path)
        expected = module_dir / "ModuleData" / entry.path
        results.extend(
            validate_file_refs(entry.xml_id, entry.path, xml_files, resolver, expected)
        )

    return results
