# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
[build].build must actually run.

It was parsed and never executed: `build_commands` was defined on the config
and consumed nowhere, so eleven catalog apps declared build steps that silently
did nothing. They mostly survived because their toolchain happened to do the
equivalent — until one asked for something it did not (isso's JS bundles), and
the app shipped without the thing it exists to serve.

A declared step that does not run is a lie, whatever the toolchain covers by
coincidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from pathlib import Path


def _config(tmp_path: Path, toml: str) -> AppConfig:
    # from_dir takes the APP directory; the recipe lives in its src/ subtree,
    # mirroring /home/hop3/apps/<app>/src on a real server.
    src = tmp_path / "src"
    src.mkdir()
    (src / "hop3.toml").write_text(toml)
    return AppConfig.from_dir(tmp_path)


def test_build_commands_are_exposed_to_the_deploy(tmp_path) -> None:
    config = _config(
        tmp_path,
        '[build]\nbuilder = "local"\nbuild = ["npm ci", "npm run build"]\n',
    )

    assert config.build_steps == ["npm ci", "npm run build"]


def test_a_single_command_is_a_list_of_one(tmp_path) -> None:
    config = _config(tmp_path, '[build]\nbuilder = "local"\nbuild = "make miniflux"\n')

    assert config.build_steps == ["make miniflux"]


def test_no_build_section_yields_nothing(tmp_path) -> None:
    config = _config(tmp_path, '[metadata]\nid = "x"\n')

    assert config.build_steps == []


@pytest.mark.parametrize("hook", ["before-build", "after-build"])
def test_build_is_distinct_from_the_other_hooks(tmp_path, hook) -> None:
    """The three hooks are separate; declaring one must not populate another."""
    config = _config(tmp_path, f'[build]\nbuilder = "local"\n"{hook}" = "fetch.sh"\n')

    assert config.build_steps == []
