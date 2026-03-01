"""
XSD resolver abstractions.

Provides a Protocol-based abstraction for "given a schema id, return the Path
to the XSD file to validate against".  Two concrete implementations ship here:

  DirectoryXsdResolver
      Simple lookup: <xsd_dir>/<xml_id>.xsd.
      Used for normal validation.

  XsltPatchedXsdResolver
      Wraps any base resolver.  For each schema id it applies an XSLT
      stylesheet to the base XSD, writes the result to a temporary file, and
      returns that path.  Results are cached in memory so the transform runs
      at most once per schema id per session.

      Requires lxml (already a hard dependency for XSD validation).  When lxml
      is unavailable, construction raises ImportError so the caller can give a
      useful error message before the validator proceeds.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class XsdResolver(Protocol):
    """Return the Path to the XSD file for *xml_id* (the file may not exist)."""

    def resolve(self, xml_id: str) -> Path:
        ...


class DirectoryXsdResolver:
    """Look up ``<xsd_dir>/<xml_id>.xsd``."""

    def __init__(self, xsd_dir: Path) -> None:
        self._xsd_dir = xsd_dir

    def resolve(self, xml_id: str) -> Path:
        return self._xsd_dir / f"{xml_id}.xsd"


class XsltPatchedXsdResolver:
    """
    Apply an XSLT stylesheet to the base XSD before validation.

    For schema ids whose XSD does not exist in the base resolver the path is
    returned unchanged; the caller (core.py) will mark those files as skipped.
    """

    def __init__(self, base: XsdResolver, xslt_path: Path) -> None:
        try:
            from lxml import etree as _etree  # noqa: F401 — import check only
        except ImportError as exc:
            raise ImportError(
                "--bannerlord-xml-expanded-api requires lxml: pip install lxml"
            ) from exc

        if not xslt_path.is_file():
            raise FileNotFoundError(f"XSLT stylesheet not found: {xslt_path}")

        self._base = base
        self._xslt_path = xslt_path
        self._cache: dict[str, Path] = {}
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="bannerlord_xsd_expanded_")
        self._transform = None  # compiled lazily on first use

    def resolve(self, xml_id: str) -> Path:
        if xml_id in self._cache:
            return self._cache[xml_id]

        base_xsd = self._base.resolve(xml_id)
        if not base_xsd.is_file():
            return base_xsd  # propagate "not found" — core.py handles it

        patched = self._patch(xml_id, base_xsd)
        self._cache[xml_id] = patched
        return patched

    def _patch(self, xml_id: str, base_xsd: Path) -> Path:
        from lxml import etree

        if self._transform is None:
            xslt_doc = etree.parse(str(self._xslt_path))
            self._transform = etree.XSLT(xslt_doc)

        xsd_doc = etree.parse(str(base_xsd))
        result = self._transform(xsd_doc)

        out_path = Path(self._tmp_dir.name) / f"{xml_id}.xsd"
        with out_path.open("wb") as fh:
            fh.write(etree.tostring(result, xml_declaration=True, encoding="UTF-8"))
        return out_path
