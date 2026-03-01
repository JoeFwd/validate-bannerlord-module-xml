"""
Output formatters.

Two output modes are supported:
  - print_human()              — coloured, readable terminal output
  - emit_github_annotations()  — GitHub Actions ::error/::warning workflow commands
                                 for inline PR diff annotations
"""
from __future__ import annotations

import os
from pathlib import Path

from .models import ValidationResult


def _relative_path(path: str, base: Path) -> str:
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return path


def emit_github_annotations(
    all_results: dict[str, list[ValidationResult]],
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
                cmd = issue.severity
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
            label = _relative_path(r.xml_path, base)
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
                if verbose:
                    print(f"  WARN  {label}")
                    for w in r.warnings:
                        print(f"          WARN:  {w}")
            elif verbose:
                print(f"  OK    {label}")

        if failed:
            print(f"  => {len(failed)} file(s) FAILED\n")
        else:
            print(f"  => All files passed\n")
