"""
Shared validation core.

validate_file_refs() is the single DRY implementation used by both
the SubModule.xml validator and the project.mbproj validator.
Callers resolve their own file lists; this function only handles
XSD lookup and the per-file validation loop.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .backends import get_backend
from .models import ValidationResult


def validate_file_refs(
    xml_id: str,
    declared_path: str,
    xml_files: list[Path],
    xsd_dir: Path,
    expected_xml_path: Optional[Path] = None,
) -> list[ValidationResult]:
    """
    Validate a resolved list of XML files against a single XSD schema.

    Args:
        xml_id:            Schema ID — used as the XSD filename stem.
        declared_path:     Original path string from the source file, used in
                           "file not found" skip messages.
        xml_files:         Resolved absolute paths to validate. Pass an empty
                           list when the declared file(s) could not be found.
        xsd_dir:           Directory that contains the XSD files.
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

    backend = get_backend()
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
            result.issues = backend(xml_path, xsd_path)
        results.append(result)

    return results
