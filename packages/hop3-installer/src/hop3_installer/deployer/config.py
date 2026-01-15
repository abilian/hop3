# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for Hop3 deployer."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import env_bool, env_list, env_str, find_project_root

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
    ssh_port: int = 22

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
    quiet: bool = False
    log_file: Path | None = None
    dry_run: bool = False
    no_cli_setup: bool = False

    # Paths (auto-detected)
    project_root: Path = field(
        default_factory=lambda: find_project_root(Path(__file__).parent)
    )

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
        """Path to the server installer script.

        Returns the bundled installer from dist/, regenerating if source is newer.
        """
        dist_installer = self.project_root / "dist" / "install-server.py"

        # Check if bundle exists and is up-to-date with source files
        if dist_installer.exists():
            if not self._is_bundle_stale(dist_installer):
                return dist_installer

        # Generate the bundled installer
        self._generate_bundled_installer(dist_installer)
        return dist_installer

    def _is_bundle_stale(self, bundle_path: Path) -> bool:
        """Check if bundle is older than any source module.

        Args:
            bundle_path: Path to the bundled installer.

        Returns:
            True if any source module is newer than the bundle.
        """
        from hop3_installer.bundler import SERVER_MODULES, SRC_DIR

        bundle_mtime = bundle_path.stat().st_mtime

        for module_path in SERVER_MODULES:
            source_file = SRC_DIR / module_path
            if source_file.exists():
                if source_file.stat().st_mtime > bundle_mtime:
                    return True

        return False

    def _generate_bundled_installer(self, output_path: Path) -> None:
        """Generate the bundled installer using the bundler."""
        from hop3_installer.bundler import bundle_installer

        # Ensure dist directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate the bundled installer
        source = bundle_installer("server")
        output_path.write_text(source)
        output_path.chmod(0o755)

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
            HOP3_QUIET - Quiet mode (1 or true)
            HOP3_DOCKER - Use Docker instead of SSH (1 or true)
        """
        host = env_str("HOP3_DEV_HOST") or env_str("HOP3_TEST_SERVER")
        features = env_list("HOP3_WITH")

        return cls(
            host=host,
            use_docker=env_bool("HOP3_DOCKER"),
            ssh_user=env_str("HOP3_SSH_USER", DEFAULT_SSH_USER),
            branch=env_str("HOP3_BRANCH", DEFAULT_BRANCH),
            use_local_code=env_bool("HOP3_LOCAL"),
            clean_before=env_bool("HOP3_CLEAN"),
            with_features=features or ["docker"],
            admin_domain=env_str("HOP3_ADMIN_DOMAIN"),
            admin_user=env_str("HOP3_ADMIN_USER", DEFAULT_ADMIN_USER),
            admin_email=env_str("HOP3_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
            admin_password=env_str("HOP3_ADMIN_PASSWORD", ""),
            verbose=env_bool("HOP3_VERBOSE"),
            quiet=env_bool("HOP3_QUIET"),
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

        if self.verbose and self.quiet:
            errors.append("Cannot use both --verbose and --quiet")

        return errors
