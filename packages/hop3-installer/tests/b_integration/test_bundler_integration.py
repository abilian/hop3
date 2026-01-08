# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for hop3_installer.bundler module.

These tests actually generate bundled installers and verify they work.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from hop3_installer.bundler import bundle_installer, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path

# =============================================================================
# Bundle Generation Tests
# =============================================================================


class TestBundleGeneration:
    """Tests for bundle_installer function."""

    def test_generates_cli_bundle(self):
        """bundle_installer should generate valid CLI bundle."""
        source = bundle_installer("cli")

        # Should be non-empty
        assert len(source) > 1000

        # Should be valid Python
        assert validate_bundle(source) is True

        # Should contain expected elements
        assert "#!/usr/bin/env python3" in source
        assert "AUTO-GENERATED FILE" in source
        assert "def main(" in source

    def test_generates_server_bundle(self):
        """bundle_installer should generate valid server bundle."""
        source = bundle_installer("server")

        # Should be non-empty
        assert len(source) > 1000

        # Should be valid Python
        assert validate_bundle(source) is True

        # Should contain expected elements
        assert "#!/usr/bin/env python3" in source
        assert "AUTO-GENERATED FILE" in source
        assert "def main(" in source

    def test_invalid_type_defaults_to_server(self):
        """bundle_installer defaults to server for unknown types.

        Note: This is the current behavior. Ideally it should raise ValueError.
        """
        source = bundle_installer("invalid")
        # Should generate server bundle (current fallback behavior)
        assert validate_bundle(source) is True
        # Contains server-specific content
        assert "nginx" in source.lower()

    def test_cli_bundle_contains_no_relative_imports(self):
        """CLI bundle should not contain relative imports."""
        source = bundle_installer("cli")

        # Should not have relative imports
        assert "from ." not in source
        assert "from .." not in source

    def test_server_bundle_contains_no_relative_imports(self):
        """Server bundle should not contain relative imports."""
        source = bundle_installer("server")

        # Should not have relative imports
        assert "from ." not in source
        assert "from .." not in source

    def test_bundles_are_self_contained(self):
        """Bundles should not import from hop3_installer."""
        cli_source = bundle_installer("cli")
        server_source = bundle_installer("server")

        for source in [cli_source, server_source]:
            assert "from hop3_installer" not in source
            assert "import hop3_installer" not in source


# =============================================================================
# Bundle Execution Tests
# =============================================================================


class TestBundleExecution:
    """Tests that verify bundled scripts can actually be executed."""

    def test_cli_bundle_shows_help(self, tmp_path: Path):
        """CLI bundle should execute and show help."""
        source = bundle_installer("cli")
        script = tmp_path / "install-cli.py"
        script.write_text(source)
        script.chmod(0o755)

        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "hop3" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_server_bundle_shows_help(self, tmp_path: Path):
        """Server bundle should execute and show help."""
        source = bundle_installer("server")
        script = tmp_path / "install-server.py"
        script.write_text(source)
        script.chmod(0o755)

        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "hop3" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_cli_bundle_syntax_check(self, tmp_path: Path):
        """CLI bundle should pass Python syntax check."""
        source = bundle_installer("cli")
        script = tmp_path / "install-cli.py"
        script.write_text(source)

        # Use python -m py_compile for syntax check
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_server_bundle_syntax_check(self, tmp_path: Path):
        """Server bundle should pass Python syntax check."""
        source = bundle_installer("server")
        script = tmp_path / "install-server.py"
        script.write_text(source)

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Syntax error: {result.stderr}"


# =============================================================================
# Bundle Content Tests
# =============================================================================


class TestBundleContent:
    """Tests for bundle content integrity."""

    def test_cli_bundle_has_version_check(self):
        """CLI bundle should include Python version check."""
        source = bundle_installer("cli")
        assert "MIN_PYTHON" in source
        assert "version_info" in source

    def test_server_bundle_has_version_check(self):
        """Server bundle should include Python version check."""
        source = bundle_installer("server")
        assert "MIN_PYTHON" in source
        assert "version_info" in source

    def test_bundles_have_license_header(self):
        """Bundles should include license header."""
        for installer_type in ["cli", "server"]:
            source = bundle_installer(installer_type)
            assert "Apache-2.0" in source
            assert "Abilian" in source

    def test_bundles_have_generation_date(self):
        """Bundles should include generation timestamp."""
        for installer_type in ["cli", "server"]:
            source = bundle_installer(installer_type)
            assert "Generated by hop3-installer bundler" in source

    def test_cli_bundle_has_cli_functionality(self):
        """CLI bundle should have CLI-specific functions."""
        source = bundle_installer("cli")
        # CLI installer should have path modification logic
        assert "bin_dir" in source.lower() or "path" in source.lower()

    def test_server_bundle_has_server_functionality(self):
        """Server bundle should have server-specific functions."""
        source = bundle_installer("server")
        # Server installer should have system package installation
        assert "apt" in source.lower() or "dnf" in source.lower()
        assert "nginx" in source.lower()
