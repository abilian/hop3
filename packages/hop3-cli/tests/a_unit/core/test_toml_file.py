# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A TOML file the CLI reads is either absent or valid: never quietly empty."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_cli.core.toml_file import read_toml
from hop3_cli.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def test_an_absent_file_reads_as_empty(tmp_path: Path) -> None:
    assert read_toml(tmp_path / "hop3.toml") == {}


def test_a_valid_file_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "demo"\n')

    assert read_toml(path) == {"project": {"name": "demo"}}


def test_a_malformed_file_raises_naming_it(tmp_path: Path) -> None:
    path = tmp_path / "hop3.toml"
    path.write_text("[build\n")

    with pytest.raises(ConfigError, match=r"hop3\.toml is not valid TOML"):
        read_toml(path)


def test_an_unreadable_file_raises_naming_it(tmp_path: Path) -> None:
    path = tmp_path / "hop3.toml"
    path.mkdir()  # exists, but cannot be opened as a file

    with pytest.raises(ConfigError, match=r"cannot read .*hop3\.toml"):
        read_toml(path)
