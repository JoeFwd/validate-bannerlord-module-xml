"""
project.mbproj validator.

Parses <file> declarations from a project.mbproj, resolves each path relative
to the module root (parent of the directory containing the .mbproj file), and
validates them against the matching XSD schema.

XSD stem resolution for mbproj entries
---------------------------------------
The mbproj ``id`` attribute is a project-scoped identifier (e.g.
``soln_monsters``) that does *not* always match the XSD filename stem (e.g.
``Monsters``).  Resolution uses the following priority order:

  1. If ``<id>.xsd`` exists on disk, use the id directly (the common case for
     ``soln_action_sets``, ``soln_skins``, etc.).
  2. If the id is in the known override table ``_MBPROJ_ID_TO_XSD_STEM``, use
     the mapped stem.  This covers the confirmed mismatches between Native's
     project.mbproj ids and the XmlSchemas/ directory.
  3. If ``<type>.xsd`` exists on disk, use the type attribute as a forward-
     compatible fallback for future engine types.
  4. Fall back to the raw id; core.py will mark the file as skipped if the XSD
     still cannot be found.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .core import validate_file_refs
from .models import ValidationResult
from .xsd_resolver import XsdResolver

# Maps mbproj <file id="..."> values that do NOT match the XSD filename stem
# to the correct XSD stem.  Confirmed by cross-referencing Native's
# project.mbproj with the XmlSchemas/ directory and with Native's SubModule.xml
# (which uses the canonical schema-type ids that match XSD names).
#
# How to extend: run the validator with --mbproj and look for "XSD schema not
# found" skips on files you know have a schema; add an entry here.
_MBPROJ_ID_TO_XSD_STEM: dict[str, str] = {
    "soln_monsters":       "Monsters",
    "soln_item_modifiers": "ItemModifiers",
}


@dataclass
class MbProjEntry:
    xml_id: str   # <file id="...">   — project-scoped identifier
    xml_type: str # <file type="..."> — schema-type identifier
    name: str     # <file name="..."> — path relative to the module root


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
        xml_type = (file_el.get("type") or "").strip()
        name = (file_el.get("name") or "").strip()
        if not xml_id or not name:
            continue
        entries.append(MbProjEntry(xml_id=xml_id, xml_type=xml_type, name=name))

    return entries


def _resolve_xsd_stem(entry: MbProjEntry, resolver: XsdResolver) -> str:
    """
    Return the XSD filename stem to use for *entry*, following the resolution
    order described in the module docstring.
    """
    # 1. id matches an existing XSD directly
    if resolver.resolve(entry.xml_id).is_file():
        return entry.xml_id

    # 2. known id override
    if entry.xml_id in _MBPROJ_ID_TO_XSD_STEM:
        return _MBPROJ_ID_TO_XSD_STEM[entry.xml_id]

    # 3. type attribute matches an existing XSD
    if entry.xml_type and resolver.resolve(entry.xml_type).is_file():
        return entry.xml_type

    # 4. fall back — will be reported as skipped by core.py
    return entry.xml_id


def validate_mbproj(
    mbproj_path: Path,
    resolver: XsdResolver,
) -> list[ValidationResult]:
    """
    Validate all XML files declared in a project.mbproj.

    Path resolution: <file name="..."> is relative to the module root, which
    is the parent directory of the directory that contains the .mbproj file.

      project.mbproj at:  <ModuleRoot>/ModuleData/project.mbproj
      module root:        <ModuleRoot>/
      name="ModuleData/skins.xml"  ->  <ModuleRoot>/ModuleData/skins.xml

    This also covers non-standard locations (e.g. RBMXML/project.mbproj):
      module root = <ModuleRoot>/
      name="RBMXML/combat.xml"     ->  <ModuleRoot>/RBMXML/combat.xml

    Raises FileNotFoundError if the .mbproj file does not exist.
    """
    if not mbproj_path.is_file():
        raise FileNotFoundError(f"project.mbproj not found: {mbproj_path}")

    module_root = mbproj_path.parent.parent
    results: list[ValidationResult] = []

    for entry in parse_mbproj(mbproj_path):
        xml_path = module_root / entry.name
        xml_files = [xml_path] if xml_path.is_file() else []
        xsd_stem = _resolve_xsd_stem(entry, resolver)
        results.extend(
            validate_file_refs(xsd_stem, entry.name, xml_files, resolver, xml_path)
        )

    return results
