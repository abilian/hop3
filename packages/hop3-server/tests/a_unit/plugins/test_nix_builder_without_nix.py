# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A Nix app on a server installed without Nix.

`[build].builder = "nix"` selects the builder without `accept()`, so the build
itself is where a missing Nix surfaces. It used to run `nix-build` anyway and
report `bash: nix-build: command not found`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.plugins.build.nix.builder import NixBuilder

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def builder(tmp_path: Path, monkeypatch) -> NixBuilder:
    """A builder on a host with no Nix profile and nothing on PATH."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(
        NixBuilder, "_get_nix_profile_paths", lambda self: [tmp_path / "no-nix.sh"]
    )
    (tmp_path / "hop3.nix").write_text("{ pkgs ? import <nixpkgs> {} }: {}")
    context = BuildContext(
        app_name="testapp", source_path=tmp_path, app_config={"hop3_config": {}}
    )
    return NixBuilder(context)


def test_build_names_the_missing_nix_and_the_fix(builder: NixBuilder):
    with pytest.raises(Abort, match="--with nix") as excinfo:
        builder.build()
    assert "Nix is not installed on this server" in str(excinfo.value)


def test_accept_still_declines_with_a_reason(builder: NixBuilder):
    assert builder.accept() is False
    assert builder.rejection_reason == "nix command not found"
