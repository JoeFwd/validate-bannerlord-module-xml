from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from validator.core import validate_file_refs


class StubResolver:
    def __init__(self, xsd_path: Path) -> None:
        self.xsd_path = xsd_path

    def resolve(self, xml_id: str) -> Path:
        return self.xsd_path


class ValidateFileRefsTests(TestCase):
    def test_skips_xsl_and_xslt_files_case_insensitively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            resolver = StubResolver(root / "schema.xsd")

            for suffix in (".xsl", ".xslt", ".XSL", ".XSLT"):
                stylesheet = root / f"transform{suffix}"
                stylesheet.touch()

                result = validate_file_refs(
                    "schema", stylesheet.name, [stylesheet], resolver
                )[0]

                self.assertTrue(result.skipped)
                self.assertEqual(result.skip_reason, "XSLT stylesheet ignored")
                self.assertFalse(result.errors)

    def test_xml_files_keep_existing_validation_behavior(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            xml_file = root / "data.xml"
            xml_file.touch()
            missing_xsd = root / "schema.xsd"

            result = validate_file_refs(
                "schema", xml_file.name, [xml_file], StubResolver(missing_xsd)
            )[0]

            self.assertTrue(result.skipped)
            self.assertEqual(
                result.skip_reason, "XSD schema not found: schema.xsd"
            )
