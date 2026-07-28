# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`hop3 scaffold` — the starter hop3.toml.

Its main job is the `#:schema` line: authors write recipes in their own repos,
where neither of our .taplo.toml files reaches them, so this is the only thing
that gets their editor validating as they type.
"""

from __future__ import annotations

import pytest
import tomllib
from hop3_cli.commands.local.scaffold_cmd import (
    SCHEMA_URL,
    detect_toolchain,
    handle_scaffold,
    render,
    suggest_app_id,
)


def _scaffold(tmp_path, monkeypatch, args=()):
    monkeypatch.chdir(tmp_path)
    handle_scaffold(list(args), config=None, printer=None)
    return tmp_path / "hop3.toml"


def test_the_schema_directive_comes_first(tmp_path, monkeypatch) -> None:
    """
    Taplo reads `#:schema` only as the FIRST line; anywhere else it is a comment.

    Getting this wrong produces a file that looks right and validates nothing.
    """
    target = _scaffold(tmp_path, monkeypatch)

    assert target.read_text().splitlines()[0] == f"#:schema {SCHEMA_URL}"


def test_the_app_id_is_valid(tmp_path, monkeypatch) -> None:
    """
    A scaffolded id must pass the server's own name rules.

    Directory names carry underscores, dots and capitals that app names do not
    allow — handing someone a starting point that fails validation wastes the
    first thing they try.
    """
    directory = tmp_path / "My_Cool.App"
    directory.mkdir()

    target = _scaffold(directory, monkeypatch)

    assert 'id = "my-cool-app"' in target.read_text()


def test_an_unnameable_directory_still_yields_something_valid(tmp_path) -> None:
    directory = tmp_path / "___"
    directory.mkdir()

    assert suggest_app_id(directory) == "my-app"


def test_an_existing_config_is_never_overwritten(tmp_path, monkeypatch) -> None:
    """
    A hop3.toml is hand-edited and may be the only record of how an app deploys.

    Silently replacing it would be unrecoverable, so this refuses by default.
    """
    (tmp_path / "hop3.toml").write_text("[metadata]\nid = 'precious'\n")

    target = _scaffold(tmp_path, monkeypatch)

    assert "precious" in target.read_text()


def test_force_overwrites_deliberately(tmp_path, monkeypatch) -> None:
    (tmp_path / "hop3.toml").write_text("[metadata]\nid = 'old'\n")

    target = _scaffold(tmp_path, monkeypatch, args=["--force"])

    assert "old" not in target.read_text()


def test_toolchain_is_reported_but_not_declared(tmp_path, monkeypatch) -> None:
    """
    Detection is shown to the author, never written into the file.

    Hop3 re-detects at deploy time, so a hard-coded toolchain is only a thing to
    get wrong later when the project changes shape.
    """
    (tmp_path / "package.json").write_text("{}")

    target = _scaffold(tmp_path, monkeypatch)
    content = target.read_text()

    assert detect_toolchain(tmp_path) == "node"
    assert "Detected a node project" in content
    assert "toolchain =" not in content


def test_an_unrecognised_project_still_scaffolds(tmp_path, monkeypatch) -> None:
    """No markers is not an error — Hop3 still tries, and says so."""
    target = _scaffold(tmp_path, monkeypatch)

    assert detect_toolchain(tmp_path) is None
    assert "No known project markers" in target.read_text()


def test_the_generated_file_parses_as_toml() -> None:
    """A starter that does not parse is worse than no starter."""
    parsed = tomllib.loads(render("my-app", "python"))

    assert parsed["metadata"]["id"] == "my-app"


# --help must be inert


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_writes_no_file(tmp_path, monkeypatch, capsys, flag) -> None:
    """
    Asking for help must never have a side effect.

    This command writes into the working directory, so a missed --help left an
    unwanted hop3.toml wherever the operator happened to be standing — which is
    exactly what it did.
    """
    monkeypatch.chdir(tmp_path)

    handle_scaffold([flag], config=None, printer=None)

    assert not (tmp_path / "hop3.toml").exists()
    assert "Usage: hop3 scaffold" in capsys.readouterr().out


def test_help_wins_over_force(tmp_path, monkeypatch, capsys) -> None:
    """`--help --force` asks a question; it does not answer it destructively."""
    existing = tmp_path / "hop3.toml"
    existing.write_text("[metadata]\nid = 'precious'\n")
    monkeypatch.chdir(tmp_path)

    handle_scaffold(["--help", "--force"], config=None, printer=None)

    assert "precious" in existing.read_text()
    assert "Usage: hop3 scaffold" in capsys.readouterr().out
