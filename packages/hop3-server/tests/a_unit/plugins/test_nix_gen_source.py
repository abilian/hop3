# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for Source dataclass and its methods."""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen.spec import Source

# --- Source.as_nix ---


def test_as_nix_simple():
    s = Source(url="https://example.com/app.tar.gz", sha256="abc123")
    nix = s.as_nix("app-src")
    assert "app-src = pkgs.fetchurl" in nix
    assert '"https://example.com/app.tar.gz"' in nix
    assert '"abc123"' in nix
    assert "executable" not in nix


def test_as_nix_executable():
    s = Source(url="https://example.com/bin", sha256="def456", executable=True)
    nix = s.as_nix("my-bin")
    assert "executable = true;" in nix


def test_as_nix_binding_name_preserved():
    s = Source(url="https://x.com/f", sha256="x")
    nix = s.as_nix("custom-name-123")
    assert "custom-name-123 = pkgs.fetchurl" in nix


# --- Source.archive properties ---


def test_needs_unzip_true():
    assert Source(url="x", sha256="x", archive="zip").needs_unzip is True


def test_needs_unzip_false():
    assert Source(url="x", sha256="x", archive="tar-gz").needs_unzip is False
    assert Source(url="x", sha256="x").needs_unzip is False


def test_is_archive():
    assert Source(url="x", sha256="x", archive="tar-gz").is_archive is True
    assert Source(url="x", sha256="x", archive="zip").is_archive is True
    assert Source(url="x", sha256="x").is_archive is False


# --- Source.unpack_command ---


def test_unpack_tar_gz():
    s = Source(url="x", sha256="x", archive="tar-gz")
    assert s.unpack_command(1) == "tar xzf $src --strip-components=1"
    assert s.unpack_command(2) == "tar xzf $src --strip-components=2"


def test_unpack_tar_bz2():
    s = Source(url="x", sha256="x", archive="tar-bz2")
    assert "xjf" in s.unpack_command(1)


def test_unpack_tar_xz():
    s = Source(url="x", sha256="x", archive="tar-xz")
    assert "xJf" in s.unpack_command(1)


def test_unpack_zip():
    s = Source(url="x", sha256="x", archive="zip")
    assert s.unpack_command(1) == "unzip -q $src"


def test_unpack_none_raises():
    s = Source(url="x", sha256="x")
    with pytest.raises(ValueError, match="Cannot unpack"):
        s.unpack_command(1)


def test_unpack_unknown_raises():
    s = Source(url="x", sha256="x", archive="rar")
    with pytest.raises(ValueError, match="Cannot unpack"):
        s.unpack_command(1)
