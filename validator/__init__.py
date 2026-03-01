"""
bannerlord-xml-validator public API.

Programmatic usage:

    from validator import validate_module, validate_mbproj
    from validator import ValidationResult, ValidationIssue

    results = validate_module(Path("../MyModule"), Path("XmlSchemas/v1.3"))
    for r in results:
        if not r.is_valid:
            print(r.errors)
"""
from .mbproj import validate_mbproj
from .models import ValidationIssue, ValidationResult
from .submodule import validate_module

__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "validate_module",
    "validate_mbproj",
]
