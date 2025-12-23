# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for Hop3 deployer."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

# Default values
DEFAULT_BRANCH = "devel"
DEFAULT_SSH_USER = "root"
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_EMAIL = "admin@example.com"

# Docker configuration
DOCKER_IMAGE = "ubuntu:24.04"
DOCKER_CONTAINER_NAME = "hop3-dev"


@dataclass
class DeployConfig:
    """Configuration for deployment."""

    # Target (either host or docker)
    host: str | None = None
    use_docker: bool = False
    docker_image: str = DOCKER_IMAGE
    docker_container: str = DOCKER_CONTAINER_NAME

    # SSH settings
    ssh_user: str = DEFAULT_SSH_USER

    # Installation settings
    branch: str = DEFAULT_BRANCH
    use_local_code: bool = False
    skip_install: bool = False
    clean_before: bool = False
    with_features: list[str] = field(default_factory=list)

    # Admin user settings
    admin_domain: str | None = None
    admin_user: str = DEFAULT_ADMIN_USER
    admin_email: str = DEFAULT_ADMIN_EMAIL
    admin_password: str = ""

    # Output settings
    verbose: bool = False
    dry_run: bool = False
    no_cli_setup: bool = False

    # Paths (auto-detected)
    project_root: Path = field(default_factory=lambda: _find_project_root())

    def __post_init__(self):
        """Validate and set defaults after initialization."""
        # Generate admin password if not provided
        if not self.admin_password:
            self.admin_password = secrets.token_urlsafe(16)

        # Default features
        if not self.with_features:
            self.with_features = ["docker"]

    @property
    def ssh_target(self) -> str:
        """Get SSH target string (user@host)."""
        if not self.host:
            raise ValueError("Host not set")
        return f"{self.ssh_user}@{self.host}"

    @property
    def installer_path(self) -> Path:
        """Path to the server installer script."""
        return self.project_root / "installer" / "install-server.py"

    @property
    def packages_path(self) -> Path:
        """Path to packages directory."""
        return self.project_root / "packages"

    @property
    def server_package_path(self) -> Path:
        """Path to hop3-server package."""
        return self.packages_path / "hop3-server"

    @property
    def dist_path(self) -> Path:
        """Path to dist directory."""
        return self.project_root / "dist"

    @classmethod
    def from_env(cls) -> DeployConfig:
        """Create config from environment variables.

        Supported environment variables:
            HOP3_DEV_HOST / HOP3_TEST_SERVER - Target server
            HOP3_SSH_USER - SSH user (default: root)
            HOP3_BRANCH - Git branch (default: devel)
            HOP3_LOCAL - Use local code (1 or true)
            HOP3_CLEAN - Clean before deploy (1 or true)
            HOP3_WITH - Features to install (comma-separated)
            HOP3_ADMIN_DOMAIN - Admin domain
            HOP3_ADMIN_USER - Admin username
            HOP3_ADMIN_EMAIL - Admin email
            HOP3_ADMIN_PASSWORD - Admin password
            HOP3_VERBOSE - Verbose output (1 or true)
            HOP3_DOCKER - Use Docker instead of SSH (1 or true)
        """
        host = os.environ.get("HOP3_DEV_HOST") or os.environ.get("HOP3_TEST_SERVER")
        use_docker = os.environ.get("HOP3_DOCKER", "").lower() in ("1", "true")

        features_str = os.environ.get("HOP3_WITH", "")
        features = [f.strip() for f in features_str.split(",") if f.strip()]

        return cls(
            host=host,
            use_docker=use_docker,
            ssh_user=os.environ.get("HOP3_SSH_USER", DEFAULT_SSH_USER),
            branch=os.environ.get("HOP3_BRANCH", DEFAULT_BRANCH),
            use_local_code=os.environ.get("HOP3_LOCAL", "").lower() in ("1", "true"),
            clean_before=os.environ.get("HOP3_CLEAN", "").lower() in ("1", "true"),
            with_features=features or ["docker"],
            admin_domain=os.environ.get("HOP3_ADMIN_DOMAIN"),
            admin_user=os.environ.get("HOP3_ADMIN_USER", DEFAULT_ADMIN_USER),
            admin_email=os.environ.get("HOP3_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
            admin_password=os.environ.get("HOP3_ADMIN_PASSWORD", ""),
            verbose=os.environ.get("HOP3_VERBOSE", "").lower() in ("1", "true"),
        )

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.use_docker and not self.host:
            errors.append(
                "No target specified. Set HOP3_DEV_HOST environment variable "
                "or use --host flag, or use --docker for local container."
            )

        if self.use_local_code and not self.server_package_path.exists():
            errors.append(f"Server package not found: {self.server_package_path}")

        if not self.use_docker and not self.installer_path.exists():
            errors.append(f"Installer not found: {self.installer_path}")

        return errors


def _find_project_root() -> Path:
    """Find the project root directory.

    Looks for pyproject.toml or .git directory.
    """
    current = Path(__file__).parent

    # Walk up to find project root
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "packages").exists():
            return parent
        if (parent / ".git").exists() and (parent / "packages").exists():
            return parent

    # Fallback to current working directory
    return Path.cwd()
