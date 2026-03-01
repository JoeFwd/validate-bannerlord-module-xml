"""
Validation backends.

Two backends are provided:
  - lxml  — full XSD schema validation (requires `pip install lxml`)
  - stdlib — well-formedness check only, emits a warning when lxml is absent

Both conform to the ValidationBackend Protocol so they are interchangeable.
Use get_backend() to obtain whichever is available at runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

from .models import ValidationIssue

try:
    from lxml import etree as lxml_etree

    _LXML_AVAILABLE = True
except ImportError:
    _LXML_AVAILABLE = False


class ValidationBackend(Protocol):
    def __call__(self, xml_path: Path, xsd_path: Path) -> list[ValidationIssue]:
        ...


def validate_with_lxml(xml_path: Path, xsd_path: Path) -> list[ValidationIssue]:
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


def validate_with_stdlib(xml_path: Path, _xsd_path: Path) -> list[ValidationIssue]:
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


def get_backend() -> ValidationBackend:
    """Return the best available validation backend."""
    return validate_with_lxml if _LXML_AVAILABLE else validate_with_stdlib


is_lxml_available: bool = _LXML_AVAILABLE
