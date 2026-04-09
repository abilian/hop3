# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the nix:eject command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.commands.nix import NixEjectCmd
from hop3.orm import App, AppRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def nix_app(db_session: Session, tmp_path: Path) -> App:
    """Create a test app with a source directory."""
    app_repo = AppRepository(session=db_session)
    app = App(name="mynixapp")
    app_repo.add(app, auto_commit=True)

    # Patch app paths to use tmp_path
    src_path = tmp_path / "src"
    src_path.mkdir(parents=True)

    return app


def _write_hop3_toml(src_path: Path, content: str) -> None:
    """Write a hop3.toml file in the source directory."""
    (src_path / "hop3.toml").write_text(content)


def _patch_app_paths(app: App, tmp_path: Path):
    """Patch app.app_path and app.src_path to use tmp_path."""
    return patch.multiple(
        type(app),
        app_path=property(lambda self: tmp_path),
        src_path=property(lambda self: tmp_path / "src"),
    )


class TestNixEjectCmd:
    """Tests for NixEjectCmd."""

    def test_no_hop3_toml(self, db_session: Session, nix_app: App, tmp_path: Path):
        """Error when app has no hop3.toml."""
        cmd = NixEjectCmd(db_session=db_session)
        with _patch_app_paths(nix_app, tmp_path):
            result = cmd.run("mynixapp")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "hop3.toml" in result[0]["text"]

    def test_no_nix_template(self, db_session: Session, nix_app: App, tmp_path: Path):
        """Error when hop3.toml has no [nix].template."""
        src_path = tmp_path / "src"
        _write_hop3_toml(src_path, '[metadata]\nid = "mynixapp"\n')

        cmd = NixEjectCmd(db_session=db_session)
        with _patch_app_paths(nix_app, tmp_path):
            result = cmd.run("mynixapp")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "No [nix].template" in result[0]["text"]

    def test_hop3_nix_already_exists(
        self, db_session: Session, nix_app: App, tmp_path: Path
    ):
        """Error when hop3.nix already exists."""
        src_path = tmp_path / "src"
        _write_hop3_toml(
            src_path,
            '[metadata]\nid = "mynixapp"\n\n'
            "[nix]\n"
            'template = "prebuilt-binary"\n'
            'url = "https://example.com/bin"\n'
            'sha256 = "abc123"\n',
        )
        # Pre-create hop3.nix
        (src_path / "hop3.nix").write_text("# existing\n")

        cmd = NixEjectCmd(db_session=db_session)
        with _patch_app_paths(nix_app, tmp_path):
            result = cmd.run("mynixapp")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "already exists" in result[0]["text"]

    def test_successful_eject(
        self, db_session: Session, nix_app: App, tmp_path: Path
    ):
        """Successfully eject a hop3.nix from template config."""
        src_path = tmp_path / "src"
        _write_hop3_toml(
            src_path,
            '[metadata]\nid = "mynixapp"\n\n'
            "[nix]\n"
            'template = "prebuilt-binary"\n'
            'url = "https://example.com/myapp-linux-amd64"\n'
            'sha256 = "0000000000000000000000000000000000000000000000000000"\n'
            'binary-name = "myapp"\n'
            'exec = "./myapp"\n',
        )

        cmd = NixEjectCmd(db_session=db_session)
        with _patch_app_paths(nix_app, tmp_path):
            result = cmd.run("mynixapp")

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Ejected" in result[0]["text"]
        assert "prebuilt-binary" in result[0]["text"]

        # Verify the file was written
        nix_file = src_path / "hop3.nix"
        assert nix_file.exists()

        content = nix_file.read_text()
        assert "pkgs" in content
        assert "mynixapp" in content
        # Should have ejection header, not generation header
        assert "Ejected from template" in content
        assert "GENERATED" not in content

    def test_app_not_found(self, db_session: Session):
        """Error when app doesn't exist."""
        cmd = NixEjectCmd(db_session=db_session)
        with pytest.raises(ValueError, match="not found"):
            cmd.run("nonexistent-app")
