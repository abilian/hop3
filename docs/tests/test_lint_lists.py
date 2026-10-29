# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A list glued to a paragraph renders as part of it, so the linter flags it."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_lists.py"
spec = importlib.util.spec_from_file_location("lint_lists", SCRIPT)
assert spec
assert spec.loader
lint_lists = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint_lists)


def glued(text: str) -> list[int]:
    return lint_lists.glued_lines(text.split("\n"))


def test_flags_a_list_glued_to_a_paragraph() -> None:
    assert glued("Common issues:\n- one\n- two") == [1]
    assert glued("Steps:\n1. one\n2. two") == [1]


def test_accepts_a_list_after_a_blank_line_or_an_opener() -> None:
    assert glued("Common issues:\n\n- one\n- two") == []
    assert glued("## Heading\n- one") == []
    assert glued("!!! note\n    text\n- one") == []
    assert glued("- one\n    nested\n- two") == []


def test_ignores_fences_and_front_matter() -> None:
    assert glued("---\ntags:\n- a\n---\n\nText") == []
    assert glued("```\nlabel:\n- x\n```") == []
    assert glued("~~~\nlabel:\n- x\n~~~") == []


def test_fix_inserts_the_blank_line(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text("Common issues:\n- one\n- two\n")
    assert lint_lists.main(["lint_lists", str(page)]) == 1
    assert lint_lists.main(["lint_lists", "--fix", str(page)]) == 0
    assert page.read_text() == "Common issues:\n\n- one\n- two\n"
    assert lint_lists.main(["lint_lists", str(page)]) == 0
