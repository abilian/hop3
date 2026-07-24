# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the help rendering helpers (ADR 036 M4)."""

from __future__ import annotations

import pytest

from hop3.commands import _base
from hop3.commands._base import NamespaceCommand
from hop3.commands._help_render import (
    classify_doc_line as _classify_doc_line,
    parse_docstring_sections as _parse_docstring_sections,
    render_subcommands as _render_subcommands,
    short_help as _short_help,
)
from hop3.commands.help import (
    CATEGORIES,
    HelpCmd,
    _category_for,
)
from hop3.lib.scanner import scan_package


@pytest.fixture(scope="module", autouse=True)
def _load_all_commands() -> None:
    """Make sure every command module is scanned so the registry is complete."""
    scan_package("hop3.commands")


# ---- Categorization ----


def test_category_for_known_commands() -> None:
    assert _category_for("deploy") == "DAILY OPERATIONS"
    assert _category_for("app") == "MANAGEMENT"
    assert _category_for("system") == "ADMINISTRATION"
    assert _category_for("help") == "UTILITIES"


def test_category_for_unknown_is_other() -> None:
    assert _category_for("zzz-nonexistent") == "OTHER"


def test_all_categories_contain_unique_commands() -> None:
    seen: set[str] = set()
    for names in CATEGORIES.values():
        for name in names:
            assert name not in seen, f"{name!r} appears in multiple categories"
            seen.add(name)


# ---- Docstring parsing ----


def test_parse_docstring_empty() -> None:
    sections = _parse_docstring_sections(None)
    assert sections == {"summary": "", "usage": [], "examples": [], "body": []}


def test_parse_docstring_summary_only() -> None:
    sections = _parse_docstring_sections("Do a thing.")
    assert sections["summary"] == "Do a thing."
    assert sections["usage"] == []
    assert sections["examples"] == []


def test_parse_docstring_with_usage_section() -> None:
    doc = """
    Do a thing.

    Usage:
        hop3 thing
        hop3 thing --flag
    """
    sections = _parse_docstring_sections(doc)
    assert sections["summary"] == "Do a thing."
    assert sections["usage"] == ["hop3 thing", "hop3 thing --flag"]


def test_parse_docstring_inline_usage() -> None:
    """`Usage: hop3 foo bar` on one line is also recognized."""
    doc = """
    Do a thing.

    Usage: hop3 thing <arg>
    """
    sections = _parse_docstring_sections(doc)
    assert "hop3 thing <arg>" in sections["usage"]


def test_parse_docstring_with_examples() -> None:
    doc = """
    Do a thing.

    Examples:
        hop3 thing foo
        hop3 thing bar --verbose
    """
    sections = _parse_docstring_sections(doc)
    assert sections["examples"] == ["hop3 thing foo", "hop3 thing bar --verbose"]


def test_parse_docstring_singular_example_header() -> None:
    """Singular 'Example:' is treated as examples."""
    doc = """
    Do a thing.

    Example:
        hop3 thing foo
    """
    sections = _parse_docstring_sections(doc)
    assert sections["examples"] == ["hop3 thing foo"]


def test_parse_docstring_mixed_sections() -> None:
    doc = """
    Do a thing.

    Usage:
        hop3 thing

    Examples:
        hop3 thing foo
    """
    sections = _parse_docstring_sections(doc)
    assert sections["summary"] == "Do a thing."
    assert sections["usage"] == ["hop3 thing"]
    assert sections["examples"] == ["hop3 thing foo"]


def test_classify_doc_line_recognizes_headers() -> None:
    assert _classify_doc_line("Usage:") == ("usage", "")
    assert _classify_doc_line("Examples:") == ("examples", "")
    assert _classify_doc_line("Example:") == ("examples", "")


def test_classify_doc_line_inline_tail() -> None:
    section, tail = _classify_doc_line("Usage: hop3 foo bar")
    assert section == "usage"
    assert tail == "hop3 foo bar"


def test_classify_doc_line_non_header() -> None:
    section, tail = _classify_doc_line("Just a regular line.")
    assert section is None
    assert tail == ""


# ---- HelpCmd detailed output structure ----


def test_detailed_help_has_d11_structure() -> None:
    """Detailed help output follows 'hop <name> — <summary>' + structured sections."""
    cmd = HelpCmd()
    result = cmd.call("help")
    text = result[0]["text"]
    # Header
    assert "hop help" in text
    assert "Display useful help messages" in text
    # Structured sections
    assert "USAGE" in text
    assert "EXAMPLES" in text


def test_detailed_help_for_namespaced_command_shows_part_of() -> None:
    """Namespaced commands (e.g., `config set`) show a 'Part of:' line."""
    cmd = HelpCmd()
    result = cmd.call("config", "set")
    text = result[0]["text"]
    assert "Part of: hop config namespace." in text


def test_detailed_help_for_top_level_no_part_of() -> None:
    """Top-level commands (length-1 tuple names) do not show 'Part of:'."""
    cmd = HelpCmd()
    result = cmd.call("help")
    text = result[0]["text"]
    assert "Part of:" not in text


# ---- SUBCOMMANDS: a namespace lists direct children, sub-namespaces collapsed ----


class _FakeCmd:
    """A stand-in command with just what the help renderer reads."""

    def __init__(self, name: tuple[str, ...], doc: str = "") -> None:
        self.name = name
        self.__doc__ = doc
        self.hidden = False


def test_render_subcommands_lists_direct_children() -> None:
    cmds = [
        _FakeCmd(("addon", "list"), "List addon instances."),
        _FakeCmd(("addon", "create"), "Create a new addon."),
    ]
    out = "\n".join(_render_subcommands(cmds, ("addon",), _short_help))
    assert "addon list" in out
    assert "List addon instances." in out


def test_render_subcommands_collapses_a_subgroup_into_one_row() -> None:
    """`addon postgres <verb>` commands appear as one `addon postgres` row."""
    cmds = [
        _FakeCmd(("addon", "list"), "List addon instances."),
        _FakeCmd(("addon", "postgres", "dump"), "Dump pg."),
        _FakeCmd(("addon", "postgres", "restore"), "Restore pg."),
    ]
    out = "\n".join(_render_subcommands(cmds, ("addon",), _short_help))
    assert "addon postgres" in out
    assert "addon postgres dump" not in out  # verbs are NOT flattened here
    assert "2 subcommands" in out  # synthesized pointer when no namespace command


def test_render_subcommands_uses_registered_subgroup_summary() -> None:
    """A registered sub-namespace command supplies the collapsed row's summary."""
    cmds = [
        _FakeCmd(("addon", "postgres"), "PostgreSQL addon operations: backup, ..."),
        _FakeCmd(("addon", "postgres", "dump"), "Dump pg."),
    ]
    out = "\n".join(_render_subcommands(cmds, ("addon",), _short_help))
    assert "PostgreSQL addon operations" in out
    assert "addon postgres dump" not in out  # still collapsed


def _fake_registry(monkeypatch, cmds) -> None:
    """Point the namespace get_help at a controlled command set."""
    monkeypatch.setattr(_base, "lookup", lambda _cls: cmds)


def test_get_help_scopes_into_a_subgroup(monkeypatch) -> None:
    """`hop addon postgres` renders the postgres subtree, not all of addon."""
    cmds = [
        _FakeCmd(("addon",), "Manage addons."),
        _FakeCmd(("addon", "postgres"), "PostgreSQL addon operations."),
        _FakeCmd(("addon", "postgres", "dump"), "Dump pg."),
        _FakeCmd(("addon", "list"), "List addons."),
    ]
    _fake_registry(monkeypatch, cmds)
    ns = NamespaceCommand()
    ns.name = ("addon",)  # instance override of the ClassVar

    text = ns.get_help(("postgres",))[0]["text"]

    assert text.splitlines()[0] == "hop addon postgres — PostgreSQL addon operations."
    assert "addon postgres dump" in text  # the subgroup's own verb is listed
    assert "addon list" not in text  # a sibling of the subgroup is not
    assert "Part of: hop addon namespace." in text


def test_get_help_bare_namespace_collapses_subgroups(monkeypatch) -> None:
    """`hop addon` shows the postgres subgroup as one row, not its verbs."""
    cmds = [
        _FakeCmd(("addon",), "Manage addons."),
        _FakeCmd(("addon", "postgres"), "PostgreSQL addon operations."),
        _FakeCmd(("addon", "postgres", "dump"), "Dump pg."),
        _FakeCmd(("addon", "list"), "List addons."),
    ]
    _fake_registry(monkeypatch, cmds)
    ns = NamespaceCommand()
    ns.name = ("addon",)

    text = ns.get_help()[0]["text"]

    assert "addon list" in text
    assert "PostgreSQL addon operations." in text  # subgroup row summary
    assert "addon postgres dump" not in text  # collapsed, not flattened
