"""
project.mbproj validator.

Parses <file> declarations from a project.mbproj, resolves each path relative
to the module root (parent of the directory containing the .mbproj file), and
validates them against the matching XSD schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .core import validate_file_refs
from .models import ValidationResult


@dataclass
class MbProjEntry:
    xml_id: str  # <file id="...">  — XSD filename stem
    name: str    # <file name="..."> — path relative to the module root


def parse_mbproj(mbproj_path: Path) -> list[MbProjEntry]:
    """
    Return all <file> declarations from a project.mbproj.

    Multiple entries may share the same id (e.g. soln_decal_textures) — each
    points to a distinct XML file and must be validated individually.
    """
    try:
        tree = ET.parse(mbproj_path)
    except ET.ParseError as exc:
        raise ValueError(f"Cannot parse {mbproj_path}: {exc}") from exc

    entries: list[MbProjEntry] = []
    for file_el in tree.getroot().findall("file"):
        xml_id = (file_el.get("id") or "").strip()
        name = (file_el.get("name") or "").strip()
        if not xml_id or not name:
            continue
        entries.append(MbProjEntry(xml_id=xml_id, name=name))

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

    for entry in parse_mbproj(mbproj_path):
        xml_path = module_root / entry.name
        xml_files = [xml_path] if xml_path.is_file() else []
        results.extend(
            validate_file_refs(entry.xml_id, entry.name, xml_files, xsd_dir, xml_path)
        )

    return results
