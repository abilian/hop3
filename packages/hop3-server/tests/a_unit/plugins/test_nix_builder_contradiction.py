# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for NixBuilder's contradiction check.

When both an explicit hop3.nix file AND a [nix].template section in
hop3.toml are present, the builder must abort with an actionable
error rather than silently picking one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.plugins.build.nix.builder import NixBuilder

if TYPE_CHECKING:
    from pathlib import Path


def _make_context(source_path: Path, app_config: dict) -> BuildContext:
    return BuildContext(
        app_name="testapp",
        source_path=source_path,
        app_config=app_config,
    )


def test_accept_with_only_hop3_nix(tmp_path: Path):
    """Hand-crafted hop3.nix only — accept (or reject if nix unavailable)."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(_make_context(tmp_path, {"hop3_config": {}}))
    # Should not raise — contradiction check passes
    try:
        builder.accept()
    except Abort:
        pytest.fail("Should not abort with only hop3.nix present")


def test_accept_with_only_nix_template(tmp_path: Path):
    """Template-only — accept (or reject if nix unavailable)."""
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )
    try:
        builder.accept()
    except Abort:
        pytest.fail("Should not abort with only [nix].template present")


def test_accept_with_neither(tmp_path: Path):
    """No hop3.nix, no template — return False, do not raise."""
    builder = NixBuilder(_make_context(tmp_path, {"hop3_config": {}}))
    assert builder.accept() is False


def test_accept_aborts_when_both_present(tmp_path: Path):
    """Both hop3.nix and [nix].template — must abort with actionable error."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )

    with pytest.raises(Abort) as exc_info:
        builder.accept()

    msg = str(exc_info.value)
    assert "hop3.nix" in msg
    assert "[nix].template" in msg
    # Error must point to a remedy
    assert "Delete hop3.nix" in msg or "Remove the [nix].template" in msg
    # Error must mention nix:eject as the conversion path
    assert "nix eject" in msg


def test_build_aborts_when_both_present(tmp_path: Path):
    """build() also defends against the contradiction (force-selected case)."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )

    with pytest.raises(Abort):
        builder.build()
