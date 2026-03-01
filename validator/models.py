from __future__ import annotations

from dataclasses import dataclass, field


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
