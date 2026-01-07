# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo context and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Literal


class OutputLevel(IntEnum):
    """Output verbosity levels."""

    SILENT = 0  # No output (errors to stderr only)
    QUIET = 1  # Minimal output (phases + results)
    NORMAL = 2  # Default (step-by-step)
    VERBOSE = 3  # Extra details + stack traces


@dataclass
class DemoResult:
    """Result of running a single demo."""

    name: str
    title: str
    status: Literal["pass", "fail", "skip"]
    duration: float  # seconds
    error: str | None = None


@dataclass
class DemoInfo:
    """Information about a demo for inventory display."""

    name: str
    title: str
    description: str
    app_name: str
    app_dir: Path
    app_type: str
    files: list[str]
    location: Path
    is_symlink: bool = False
    symlink_target: str | None = None


@dataclass
class DemoContext:
    """Context for demo execution."""

    # Backend selection
    backend: Literal["ssh", "docker"] = "ssh"

    # Server connection (for SSH backend)
    server_ip: str = ""
    ssh_user: str = "root"
    admin_domain: str | None = None  # Domain for admin UI (e.g., hop3.example.com)

    # Docker settings (for Docker backend)
    docker_image: str = "ubuntu:24.04"
    docker_container: str = "hop3-demo"

    # Admin credentials
    admin_user: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = ""

    # Demo settings
    pause_between_steps: float = 0.5
    skip_install: bool = False
    no_cleanup: bool = False
    use_local_code: bool = False
    clean_before: bool = False  # Clean server completely before running
    fail_fast: bool = False  # Stop on first failure
    preflight: bool = False  # Run preflight checks (SSH, DNS, Ubuntu version)
    verbose: bool = False
    debug: bool = False  # Maximum verbosity (--debug flag to hop3)
    output_level: OutputLevel = OutputLevel.NORMAL

    # Logging
    logs_dir: Path | None = None  # Base directory for logs (None = demos/logs/)

    # Paths
    hop3_repo: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.server_ip}"

    @property
    def hostname(self) -> str:
        """Return the base hostname for apps.

        This returns the server IP or admin domain. Individual apps should
        use unique hostnames like 'demo01.hop3.dev' to avoid nginx routing
        conflicts when multiple apps are deployed.
        """
        return self.admin_domain or self.server_ip

    def get_app_hostname(self, app_name: str) -> str:
        """Return a unique hostname for an app.

        Args:
            app_name: The name of the app (e.g., 'demo01')

        Returns:
            A unique hostname like 'demo01.hop3.dev'.
            If server_ip looks like a domain (contains '.local' or is not an IP),
            uses it as base for subdomains.
        """
        base_domain = self.admin_domain or self.server_ip

        # Check if base looks like a domain we can add subdomains to
        # (e.g., 'hop3.dev' but not '192.168.1.1')
        is_ip_address = base_domain.replace(".", "").isdigit()
        is_domain_like = (
            ".local" in base_domain
            or ".test" in base_domain
            or ".dev" in base_domain
            or (not is_ip_address and "." in base_domain)
        )

        if is_domain_like:
            # Use subdomain: demo01.hop3.dev
            return f"{app_name}.{base_domain}"

        # Fall back to server IP (all apps share same hostname - not ideal)
        return base_domain

    @property
    def installer_path(self) -> Path:
        return self.hop3_repo / "dist" / "install-server.py"

    @property
    def packages_path(self) -> Path:
        return self.hop3_repo / "packages"

    @property
    def dist_path(self) -> Path:
        return self.hop3_repo / "dist"

    _backend_instance: object = field(default=None, repr=False)

    def get_backend(self):
        """Get or create the backend instance.

        Returns:
            DemoBackend instance (SSHDemoBackend or DockerDemoBackend)
        """
        if self._backend_instance is None:
            self._backend_instance = self._create_backend()
        return self._backend_instance

    def _create_backend(self):
        """Create the appropriate backend based on configuration.

        Returns:
            DemoBackend instance (SSHDemoBackend or DockerDemoBackend)
        """
        from lib.backends import DockerDemoBackend, SSHDemoBackend

        if self.backend == "docker":
            return DockerDemoBackend(
                container_name=self.docker_container,
                image=self.docker_image,
                project_root=self.hop3_repo,
            )
        return SSHDemoBackend(
            host=self.server_ip,
            user=self.ssh_user,
        )

    def get_backend_capabilities(self) -> set[str]:
        """Get the capabilities provided by the current backend.

        Returns:
            Set of capability strings the backend supports.
            Capabilities include:
            - "docker": Docker daemon available for building/running containers
            - "systemd": Systemd init system available
            - "ssh": Direct SSH access to server

        Note: Database services (postgres, mysql, redis) are not capabilities
        but services that need to be installed/running separately.
        """
        if self.backend == "docker":
            # Docker backend runs inside a container - no Docker-in-Docker by default
            # No systemd (uses supervisor instead)
            return set()
        # SSH backend has full server access
        return {"docker", "systemd", "ssh"}

    def check_requirements(self, requires: list[str] | None) -> tuple[bool, str]:
        """Check if demo requirements are satisfied by the current backend.

        Args:
            requires: List of required capabilities (e.g., ["docker"])

        Returns:
            Tuple of (satisfied, reason) where reason explains any unmet requirement
        """
        if not requires:
            return True, ""

        capabilities = self.get_backend_capabilities()
        missing = set(requires) - capabilities

        if missing:
            return (
                False,
                f"requires {', '.join(sorted(missing))} (not available in {self.backend} backend)",
            )

        return True, ""
