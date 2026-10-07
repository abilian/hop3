# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A Nix app on a server installed without Nix.

Whether the builder is forced (`[build].builder = "nix"`, straight to
`build()`) or auto-selected (`accept()`), an app that asks for Nix is refused
with the fix. It used to run `nix-build` anyway and report `bash: nix-build:
command not found`, or be built by another builder.
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


def test_accept_refuses_rather_than_declines(builder: NixBuilder):
    """
    Declining let auto-selection move on to the next builder: an app with a
    Procfile beside its hop3.nix was built some other way, without a word.
    """
    with pytest.raises(Abort, match="--with nix"):
        builder.accept()


def test_an_app_without_nix_files_is_still_just_declined(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "Procfile").write_text("web: python app.py\n")
    context = BuildContext(
        app_name="plain", source_path=tmp_path, app_config={"hop3_config": {}}
    )
    builder = NixBuilder(context)

    assert builder.accept() is False
    assert "no hop3.nix" in builder.rejection_reason
