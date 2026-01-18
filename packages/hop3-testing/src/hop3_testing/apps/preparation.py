# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""App preparation utilities for deployment testing.

This module handles preparing test applications for deployment:
- Creating temp directory copies
- Initializing git repositories
- Creating tarballs for deployment
- Managing ENV files
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .catalog import AppSource


@dataclass
class AppPreparation:
    """Handles preparation of test applications for deployment.

    This class manages:
    - Creating a temp directory copy of the app
    - Initializing git if needed
    - Creating ENV files for nginx configuration
    - Creating deployment tarballs
    """

    app: AppSource
    """Test application source."""

    app_name: str
    """Name for the deployed app."""

    temp_dir: Path | None = field(default=None, init=False)
    """Temporary directory for prepared app."""

    def prepare(self) -> Path:
        """Prepare the application for deployment.

        Creates a temporary copy of the app with git initialized.

        Returns:
            Path to the prepared app directory
        """
        # Create temp directory
        self.temp_dir = Path("/tmp") / f"hop3-test-{self.app_name}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        # Copy app to temp directory
        shutil.copytree(self.app.path, self.temp_dir)

        # Create ENV file with nginx configuration if not present
        self._ensure_env_file()

        # Initialize git if not already initialized
        self._ensure_git_repo()

        return self.temp_dir

    def create_tarball(self) -> Path:
        """Create a git archive tarball for deployment.

        Returns:
            Path to the created tarball
        """
        if not self.temp_dir:
            self.prepare()

        tarball_path = Path("/tmp") / f"{self.app_name}.tar.gz"
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", str(tarball_path), "HEAD"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )
        return tarball_path

    def cleanup(self) -> None:
        """Remove temp directory and any created files."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None

        # Also clean up tarball if it exists
        tarball_path = Path("/tmp") / f"{self.app_name}.tar.gz"
        tarball_path.unlink(missing_ok=True)

    def _ensure_env_file(self) -> None:
        """Ensure ENV file exists with nginx configuration."""
        if not self.temp_dir:
            return

        env_file = self.temp_dir / "ENV"
        if not env_file.exists() and self.app.has_procfile:
            hostname = f"{self.app_name}.test.local"
            env_file.write_text(f"HOST_NAME={hostname}\n")

    def _ensure_git_repo(self) -> None:
        """Ensure the temp directory is a git repository."""
        if not self.temp_dir:
            return

        git_dir = self.temp_dir / ".git"
        if not git_dir.exists():
            subprocess.run(
                ["git", "init"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

    def __enter__(self) -> AppPreparation:
        """Context manager entry."""
        self.prepare()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()
