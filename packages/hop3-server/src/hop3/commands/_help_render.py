# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for rendering command help output (ADR 036 D11).

Extracted from `help.py` so that `_base.Command.get_help()` can produce the
same D11-formatted output for namespace-bare invocations (e.g., `hop3 app`)
as `HelpCmd._detailed_help` produces for `hop3 help app`. Keeping the
rendering in one place avoids format drift between the two entry points.
"""

from __future__ import annotations

# Section-header tokens recognized in command docstrings. Case-insensitive.
_SECTION_HEADERS = {
    "usage:": "usage",
    "examples:": "examples",
    "example:": "examples",
}


def parse_docstring_sections(doc: str | None) -> dict:
    """Parse a docstring into summary / usage / examples / body sections.

    Returns a dict with keys: 'summary' (str), 'usage' (list[str]),
    'examples' (list[str]), 'body' (list[str]).
    """
    result: dict = {"summary": "", "usage": [], "examples": [], "body": []}
    if not doc:
        return result

    lines = doc.expandtabs().strip().split("\n")
    first_nonempty = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_nonempty is None:
        return result
    result["summary"] = lines[first_nonempty].strip()

    current = "body"
    for raw in lines[first_nonempty + 1 :]:
        stripped = raw.strip()
        if not stripped:
            continue
        new_section, tail = classify_doc_line(stripped)
        if new_section is not None:
            current = new_section
            if tail:
                result[current].append(tail)
        else:
            result[current].append(stripped)

    return result


def classify_doc_line(stripped: str) -> tuple[str | None, str]:
    """Classify a single stripped docstring line.

    Returns (section_name_or_None, tail). If the line is a recognized section
    header, section_name is set to the target section and tail contains any
    inline content after the header. Otherwise returns (None, "").
    """
    lower = stripped.lower()
    for header, section in _SECTION_HEADERS.items():
        if lower == header:
            return section, ""
        if lower.startswith(header):
            tail = stripped.split(":", 1)[1].strip()
            return section, tail
    return None, ""


def longest_prefix_match(
    command_name: tuple[str, ...],
    commands: dict,
) -> tuple[str, ...] | None:
    """Find the longest prefix of `command_name` present in `commands`."""
    for n in range(len(command_name), 0, -1):
        key = command_name[:n]
        if key in commands:
            return key
    return None


def render_detailed_help(display: str, sections: dict) -> list[str]:
    """Render the header + USAGE + EXAMPLES + DESCRIPTION blocks (D11)."""
    output: list[str] = []
    header = (
        f"hop {display} — {sections['summary']}"
        if sections["summary"]
        else f"hop {display}"
    )
    output.append(header)
    output.append("")

    for section_name, lines in (
        ("USAGE", sections["usage"]),
        ("EXAMPLES", sections["examples"]),
        ("DESCRIPTION", sections["body"]),
    ):
        if lines:
            output.append(section_name)
            output.extend(f"  {line}" for line in lines)
            output.append("")

    return output


def render_subcommands(
    all_commands: list,
    namespace: tuple[str, ...],
    short_help_fn,
) -> list[str]:
    """Render the SUBCOMMANDS section for a namespace."""
    subs = [
        c
        for c in all_commands
        if len(c.name) > len(namespace)
        and c.name[: len(namespace)] == namespace
        and not getattr(c, "hidden", False)
    ]
    if not subs:
        return []
    subs.sort(key=lambda c: c.name)
    out = ["SUBCOMMANDS"]
    for sub in subs:
        display = " ".join(sub.name)
        out.append(f"  {display:<28} {short_help_fn(sub.__doc__)}")
    out.append("")
    return out


def short_help(docstring: str | None) -> str:
    """Extract the first non-empty line from a docstring."""
    if not docstring:
        return ""
    for line in docstring.strip().split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
