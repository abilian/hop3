# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Read diagnostic-bundle sections from disk for the drill-down view.

A bundle (ADR 043) is a directory of ``<section>.txt`` files written by
``hop3_testing.bundle.write_bundle``. Until the artifact store lands (M0b), the
Test Lab reads those files directly via the ``bundle_path`` recorded on each
failed result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.bundle import SECTION_NAMES

if TYPE_CHECKING:
    from pathlib import Path

_PLACEHOLDER = "(not collected)"


def read_bundle_sections(bundle_dir: Path) -> list[tuple[str, str]]:
    """
    Return ``(section, content)`` for sections that were actually collected.

    Sections are returned in canonical order; missing files and the
    ``(not collected)`` placeholder are skipped so the view shows only signal.
    """
    sections: list[tuple[str, str]] = []
    for name in SECTION_NAMES:
        path = bundle_dir / f"{name}.txt"
        if not path.is_file():
            continue
        content = path.read_text(errors="replace").strip()
        if content and content != _PLACEHOLDER:
            sections.append((name, content))
    return sections
