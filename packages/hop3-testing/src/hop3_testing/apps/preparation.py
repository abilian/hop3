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

    @property
    def test_hostname(self) -> str:
        """The hostname the app is deployed under (its nginx server_name).

        The HTTP validation MUST send this exact value as the Host header — a
        mismatch falls through to the platform's default_server, which 301-
        redirects (HTTP→HTTPS), so the check sees a 301 instead of the app.

        When the app declares its own hostname in hop3.toml ([domains].list or
        [env].HOST_NAME), that declared host IS the nginx server_name, so the
        probe must use it. Otherwise the harness assigns a synthetic
        `{app_name}.test.local` server_name (injected via the ENV file in
        `_ensure_env_file`): a non-public FQDN that gets a self-signed cert and
        never collides with a real domain (audit L5).
        """
        return self.app.declared_hostname or f"{self.app_name}.test.local"

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

    def cleanup(self) -> None:
        """Remove temp directory and any created files."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None

        # Also clean up tarball if it exists
        tarball_path = Path("/tmp") / f"{self.app_name}.tar.gz"
        tarball_path.unlink(missing_ok=True)

    def _ensure_env_file(self) -> None:
        """Pin a routable HOST_NAME for nginx-served apps that declare none.

        Injects `HOST_NAME={app_name}.test.local` for any app that does NOT
        declare its own hostname — Procfile-only apps AND hop3.toml apps with
        neither [domains] nor [env].HOST_NAME. That value is the nginx
        server_name the HTTP validation probes with; without it a hop3.toml
        static app gets a bare-app-name server_name (or none), so the probe's
        `{app_name}.test.local` Host misses the vhost → default_server → 301
        (audit L5).

        Skipped when the app declares its own hostname (the hop3.toml
        [env]/[domains] value wins at deploy and the probe uses it instead), or
        when an ENV file already ships with the app.
        """
        if not self.temp_dir:
            return

        env_file = self.temp_dir / "ENV"
        if not env_file.exists() and self.app.declared_hostname is None:
            env_file.write_text(f"HOST_NAME={self.test_hostname}\n")

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
                # Identity inline so the commit never depends on the caller's git
                # config — a server-resident runtime user has none ('git commit'
                # exits 128: "Please tell me who you are").
                [
                    "git",
                    "-c",
                    "user.name=Hop3 Test Lab",
                    "-c",
                    "user.email=testlab@hop3.local",
                    "commit",
                    "-m",
                    "Initial commit",
                ],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
