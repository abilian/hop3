# Copyright (c) 2023-2026, Abilian SAS

"""
Check that every Markdown list is preceded by a blank line.

Python-Markdown, which Zensical renders with, only starts a list after a blank
line. A list glued to the paragraph above it renders as that paragraph's
continuation, the items run together on one line, and GitHub (CommonMark)
renders the same source correctly, so the break is invisible until the site is
read.

Only top-level items count: an indented item belongs to a list or block that
already started. A list after a heading, a table, an admonition, a fence, an
HTML line or another item needs no blank line.

    python scripts/lint_lists.py FILE...         report, exit 1 on any finding
    python scripts/lint_lists.py --fix FILE...   insert the missing blank lines
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LIST_ITEM = re.compile(r"^([-*+]|\d+\.)\s")
FENCE = re.compile(r"^\s*(```|~~~)")
# A list may follow these lines directly.
OPENERS = ("#", "|", ">", "<", "!!!", "???", " ", "\t")


def glued_lines(lines: list[str]) -> list[int]:
    """Return the indexes of list items glued to the line above them."""
    found = []
    in_fence = False
    in_front_matter = bool(lines) and lines[0] == "---"
    for i, line in enumerate(lines):
        if in_front_matter:
            in_front_matter = i == 0 or line != "---"
            continue
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or i == 0 or not LIST_ITEM.match(line):
            continue
        prev = lines[i - 1]
        if (
            prev.strip()
            and not LIST_ITEM.match(prev)
            and not FENCE.match(prev)
            and not prev.startswith(OPENERS)
        ):
            found.append(i)
    return found


def main(argv: list[str]) -> int:
    fix = "--fix" in argv[1:]
    paths = [Path(a) for a in argv[1:] if a != "--fix"]
    total = 0
    for path in paths:
        lines = path.read_text(encoding="utf-8").split("\n")
        glued = glued_lines(lines)
        total += len(glued)
        if fix and glued:
            for i in reversed(glued):
                lines.insert(i, "")
            path.write_text("\n".join(lines), encoding="utf-8")
            continue
        for i in glued:
            print(f"{path}:{i + 1}: list glued to the line above: {lines[i - 1]!r}")
    if fix:
        print(f"Inserted {total} blank line(s) before lists.")
        return 0
    if total:
        print(f"{total} list(s) need a blank line before them.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
