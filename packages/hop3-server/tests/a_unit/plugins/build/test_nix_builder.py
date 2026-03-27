# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for NixBuilder."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.core.protocols import BuildContext
from hop3.plugins.build.nix.builder import NixBuilder

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def source_path(tmp_path: Path) -> Path:
    """Create a temporary source directory."""
    src = tmp_path / "src"
    src.mkdir()
    return src


def make_context(source_path: Path) -> BuildContext:
    """Create a BuildContext for testing."""
    return BuildContext(
        app_name="test-app",
        source_path=source_path,
        app_config={},
    )


class TestNixBuilderAccept:
    """Test NixBuilder.accept() behavior."""

    def test_accept_with_hop3_nix(self, source_path: Path) -> None:
        """NixBuilder accepts when hop3.nix exists."""
        (source_path / "hop3.nix").write_text("{ pkgs }: { package = pkgs.hello; }")
        context = make_context(source_path)

        with patch.object(NixBuilder, "_nix_available", return_value=True):
            builder = NixBuilder(context)
            assert builder.accept() is True

    def test_reject_without_hop3_nix(self, source_path: Path) -> None:
        """NixBuilder rejects when no hop3.nix."""
        context = make_context(source_path)
        builder = NixBuilder(context)

        assert builder.accept() is False
        assert "hop3.nix" in builder.rejection_reason

    def test_reject_when_nix_not_available(self, source_path: Path) -> None:
        """NixBuilder rejects when nix command not found."""
        (source_path / "hop3.nix").write_text("{ pkgs }: {}")
        context = make_context(source_path)

        with patch.object(NixBuilder, "_nix_available", return_value=False):
            builder = NixBuilder(context)
            assert builder.accept() is False
            assert "nix command" in builder.rejection_reason


class TestNixBuilderBuild:
    """Test NixBuilder.build() behavior."""

    def test_build_success(self, source_path: Path, tmp_path: Path) -> None:
        """Successful build returns BuildArtifact with RuntimeConfig."""
        # Setup hop3.nix
        (source_path / "hop3.nix").write_text("{ pkgs }: { package = pkgs.hello; }")

        # Create a mock store path with runtime.json
        store_path = tmp_path / "nix-store" / "abc123-test-app"
        (store_path / "hop3").mkdir(parents=True)
        (store_path / "hop3" / "runtime.json").write_text(
            """{
            "workers": {"web": "/nix/store/.../bin/app --bind unix:$HOP3_SOCKET"},
            "env": {"FLASK_ENV": "production"},
            "path": ["/nix/store/.../bin"]
        }"""
        )

        context = make_context(source_path)
        builder = NixBuilder(context)

        with patch.object(builder, "_nix_build", return_value=str(store_path)):
            artifact = builder.build()

        assert artifact.kind == "nix"
        assert artifact.builder == "nix"
        assert artifact.app_name == "test-app"
        assert artifact.location == str(store_path)
        assert "web" in artifact.runtime.workers
        assert artifact.runtime.env_vars["FLASK_ENV"] == "production"

    def test_build_missing_runtime_json(
        self, source_path: Path, tmp_path: Path
    ) -> None:
        """Build fails if runtime.json is missing."""
        (source_path / "hop3.nix").write_text("{ pkgs }: {}")

        # Store path without runtime.json
        store_path = tmp_path / "nix-store" / "abc123-test-app"
        store_path.mkdir(parents=True)

        context = make_context(source_path)
        builder = NixBuilder(context)

        with patch.object(builder, "_nix_build", return_value=str(store_path)):
            with pytest.raises(RuntimeError, match=r"runtime\.json"):
                builder.build()


class TestNixBuilderHelpers:
    """Test NixBuilder helper methods."""

    def test_get_build_id_extracts_hash(self, source_path: Path) -> None:
        """_get_build_id extracts hash from store path."""
        context = make_context(source_path)
        builder = NixBuilder(context)

        build_id = builder._get_build_id("/nix/store/abc123xyz-myapp-0.1.0")
        assert build_id == "abc123xyz"

    def test_get_build_id_fallback(self, source_path: Path) -> None:
        """_get_build_id returns name if no dash."""
        context = make_context(source_path)
        builder = NixBuilder(context)

        build_id = builder._get_build_id("/nix/store/nodash")
        assert build_id == "nodash"
