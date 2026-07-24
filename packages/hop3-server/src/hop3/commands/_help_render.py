# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared helpers for rendering command help output (ADR 036 D11).

Extracted from `help.py` so that `_base.Command.get_help()` can produce the
same D11-formatted output for namespace-bare invocations (e.g., `hop3 app`)
as `HelpCmd._detailed_help` produces for `hop3 help app`. Keeping the
rendering in one place avoids format drift between the two entry points.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# Section-header tokens recognized in command docstrings. Case-insensitive.
_SECTION_HEADERS = {
    "usage:": "usage",
    "examples:": "examples",
    "example:": "examples",
}


def parse_docstring_sections(doc: str | None) -> dict:
    """
    Parse a docstring into summary / usage / examples / body sections.

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
    """
    Classify a single stripped docstring line.

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
    short_help_fn: Callable[[str | None], str],
) -> list[str]:
    """
    Render the SUBCOMMANDS section for a namespace: its *direct* children only.

    Commands nested more than one level below `namespace` are collapsed into a
    single row for their sub-namespace. Under `addon`, the many
    `addon postgres <verb>` / `addon mysql <verb>` commands appear as one
    `addon postgres` / `addon mysql` row each, rather than flattening the whole
    tree — so a namespace lists what you can reach from it, and you drill in
    (`hop addon postgres`) to see a sub-namespace's own verbs. A sub-namespace's
    summary comes from its registered namespace command when there is one, else a
    synthesized pointer to drill in.
    """
    ns_len = len(namespace)
    by_name = {c.name: c for c in all_commands}

    leaves: dict[tuple[str, ...], str] = {}  # direct child -> summary
    subgroups: dict[tuple[str, ...], int] = {}  # sub-namespace -> descendant count
    for c in all_commands:
        if getattr(c, "hidden", False):
            continue
        if len(c.name) <= ns_len or c.name[:ns_len] != namespace:
            continue
        child = (*namespace, c.name[ns_len])
        if len(c.name) == ns_len + 1:
            leaves[child] = short_help_fn(c.__doc__)
        else:
            subgroups[child] = subgroups.get(child, 0) + 1

    rows: dict[tuple[str, ...], str] = {
        name: summary for name, summary in leaves.items() if name not in subgroups
    }
    for name, count in subgroups.items():
        registered = by_name.get(name)
        if registered is not None and registered.__doc__:
            rows[name] = short_help_fn(registered.__doc__)
        else:
            noun = "subcommand" if count == 1 else "subcommands"
            rows[name] = f"{count} {noun} — run 'hop {' '.join(name)}'"

    if not rows:
        return []
    out = ["SUBCOMMANDS"]
    for name in sorted(rows):
        out.append(f"  {' '.join(name):<28} {rows[name]}")
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
