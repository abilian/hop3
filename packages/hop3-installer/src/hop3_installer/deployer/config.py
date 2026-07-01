# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for Hop3 deployer."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import env_bool, env_list, env_str, find_project_root

# Import shared constants
from hop3_installer.constants import (
    ALL_FEATURES,
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USER,
    DEFAULT_BRANCH_DEVELOPMENT as DEFAULT_BRANCH,
    DEFAULT_SSH_USER,
    DOCKER_CONTAINER_NAME,
    DOCKER_IMAGE,
)
from hop3_installer.nginx_templates import is_fqdn


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
    # Explicit private key for the deploy's ssh/scp (-i). None -> ssh's default
    # identity (~/.ssh/id_*, agent). Needed when the invoking user has no usable
    # default key, e.g. a server-resident automation user.
    ssh_key: str | None = None

    # Installation settings
    branch: str = DEFAULT_BRANCH
    use_local_code: bool = False
    use_git: bool = False  # Install from git (default is PyPI)
    use_pypi: bool = False  # Explicitly request PyPI (mostly for clarity)
    pypi_version: str | None = None  # Specific PyPI version
    pypi_pre: bool = False  # Allow pre-release versions from PyPI
    skip_install: bool = False
    skip_migrations: bool = False
    clean_before: bool = False
    with_features: list[str] = field(default_factory=list)

    # Admin user settings
    admin_domain: str | None = None
    admin_user: str = DEFAULT_ADMIN_USER
    admin_email: str = DEFAULT_ADMIN_EMAIL
    admin_password: str = ""

    # ACME/Let's Encrypt settings
    acme_email: str | None = None

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
            msg = "Host not set"
            raise ValueError(msg)
        return f"{self.ssh_user}@{self.host}"

    @property
    def effective_admin_domain(self) -> str | None:
        """The hostname the Web UI is served at — the admin domain or the host.

        ``hop3-deploy --host h.example.com`` is enough to serve the Web UI at
        ``https://h.example.com/``: when ``--admin-domain`` isn't given, the
        deploy host itself becomes the admin hostname. Pass ``--admin-domain``
        to use a different one (e.g. ``admin.h.example.com``).

        Returns None for a Docker target, or when the host is not a servable
        FQDN (an IP address or ``localhost``) — there is no vhost to name, so
        the Web UI stays on port 8000.
        """
        if self.admin_domain:
            return self.admin_domain
        if self.use_docker or not self.host:
            return None
        return self.host if is_fqdn(self.host) else None

    @property
    def install_source(self) -> str:
        """Get description of the installation source."""
        if self.use_local_code:
            return "local code"
        if self.use_git:
            return f"git ({self.branch})"
        # Default is PyPI
        if self.pypi_version:
            return f"PyPI (version {self.pypi_version})"
        if self.pypi_pre:
            return "PyPI (latest including pre-releases)"
        return "PyPI (latest stable)"

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
        from hop3_installer.bundler import SERVER_MODULES, SRC_DIR  # noqa: PLC0415

        bundle_mtime = bundle_path.stat().st_mtime

        for module_path in SERVER_MODULES:
            source_file = SRC_DIR / module_path
            if source_file.exists():
                if source_file.stat().st_mtime > bundle_mtime:
                    return True

        return False

    def _generate_bundled_installer(self, output_path: Path) -> None:
        """Generate the bundled installer using the bundler."""
        from hop3_installer.bundler import bundle_installer  # noqa: PLC0415

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
    def rootd_package_path(self) -> Path:
        """Path to hop3-rootd package.

        The installer expects the daemon source as a sibling of the server
        source (``/tmp/hop3-rootd`` next to ``/tmp/hop3-server``); it's a hard
        dependency of the deploy path (nginx reloads). See
        ``server_installer.python.install_rootd_package``.
        """
        return self.packages_path / "hop3-rootd"

    @property
    def cli_package_path(self) -> Path:
        """Path to hop3-cli package.

        Uploaded next to the server source (``/tmp/hop3-cli``) so the installer
        can put the ``hop3`` client on the server. Tutorial tests run on the
        server and invoke ``hop3 deploy`` against localhost, so the CLI must be
        present there. See ``server_installer.python.install_cli_package``.
        """
        return self.packages_path / "hop3-cli"

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
            HOP3_GIT - Install from git (1 or true)
            HOP3_BRANCH - Git branch (implies HOP3_GIT if not default)
            HOP3_LOCAL - Use local code (1 or true)
            HOP3_PYPI - Install from PyPI (1 or true, this is the default)
            HOP3_PYPI_VERSION - Specific PyPI version
            HOP3_PYPI_PRE - Allow pre-release versions (1 or true)
            HOP3_CLEAN - Clean before deploy (1 or true)
            HOP3_SKIP_MIGRATIONS - Skip DB migrations after install (1 or true)
            HOP3_WITH - Features to install (comma-separated)
            HOP3_ADMIN_DOMAIN - Admin domain
            HOP3_ADMIN_USER - Admin username
            HOP3_ADMIN_EMAIL - Admin email
            HOP3_ADMIN_PASSWORD - Admin password
            HOP3_ACME_EMAIL - Email for Let's Encrypt registration
            HOP3_VERBOSE - Verbose output (1 or true)
            HOP3_QUIET - Quiet mode (1 or true)
            HOP3_DOCKER - Use Docker instead of SSH (1 or true)
        """
        host = env_str("HOP3_DEV_HOST") or env_str("HOP3_TEST_SERVER")
        features = env_list("HOP3_WITH")
        branch = env_str("HOP3_BRANCH", DEFAULT_BRANCH)

        # --branch implies --git if a non-default branch is specified
        use_git = env_bool("HOP3_GIT") or (branch != DEFAULT_BRANCH)

        return cls(
            host=host,
            use_docker=env_bool("HOP3_DOCKER"),
            ssh_user=env_str("HOP3_SSH_USER", DEFAULT_SSH_USER),
            branch=branch,
            use_local_code=env_bool("HOP3_LOCAL"),
            use_git=use_git,
            use_pypi=env_bool("HOP3_PYPI"),
            pypi_version=env_str("HOP3_PYPI_VERSION"),
            pypi_pre=env_bool("HOP3_PYPI_PRE"),
            clean_before=env_bool("HOP3_CLEAN"),
            skip_migrations=env_bool("HOP3_SKIP_MIGRATIONS"),
            with_features=features or ["docker"],
            admin_domain=env_str("HOP3_ADMIN_DOMAIN"),
            admin_user=env_str("HOP3_ADMIN_USER", DEFAULT_ADMIN_USER),
            admin_email=env_str("HOP3_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
            admin_password=env_str("HOP3_ADMIN_PASSWORD", ""),
            acme_email=env_str("HOP3_ACME_EMAIL"),
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

        # Reject unknown --with features early (before upload/connect), so a
        # typo fails here instead of deep inside install-server (ADR 052 D4).
        # postgres = always-on baseline; all = expand. Same valid set the
        # server installer's parse_features enforces.
        valid_features = ALL_FEATURES | {"postgres", "postgresql", "all"}
        unknown = [
            f for f in self.with_features if f.lower().strip() not in valid_features
        ]
        if unknown:
            errors.append(
                f"Unknown --with feature(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(sorted(ALL_FEATURES))} (or 'all')."
            )

        return errors
