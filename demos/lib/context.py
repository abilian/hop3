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

    # Server connection
    server_ip: str
    ssh_user: str = "root"
    admin_domain: str | None = None  # Domain for admin UI (e.g., hop3.example.com)

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
        use unique hostnames like 'demo01.hop3.local' to avoid nginx routing
        conflicts when multiple apps are deployed.
        """
        return self.admin_domain or self.server_ip

    def get_app_hostname(self, app_name: str) -> str:
        """Return a unique hostname for an app.

        Args:
            app_name: The name of the app (e.g., 'demo01')

        Returns:
            A unique hostname like 'demo01.hop3.local'.
            If server_ip looks like a domain (contains '.local' or is not an IP),
            uses it as base for subdomains.
        """
        base_domain = self.admin_domain or self.server_ip

        # Check if base looks like a domain we can add subdomains to
        # (e.g., 'hop3.local' but not '192.168.1.1')
        is_ip_address = base_domain.replace(".", "").isdigit()
        is_domain_like = (
            ".local" in base_domain
            or ".test" in base_domain
            or ".dev" in base_domain
            or (not is_ip_address and "." in base_domain)
        )

        if is_domain_like:
            # Use subdomain: demo01.hop3.local
            return f"{app_name}.{base_domain}"

        # Fall back to server IP (all apps share same hostname - not ideal)
        return base_domain

    @property
    def installer_path(self) -> Path:
        return self.hop3_repo / "installer" / "install-server.py"

    @property
    def packages_path(self) -> Path:
        return self.hop3_repo / "packages"

    @property
    def dist_path(self) -> Path:
        return self.hop3_repo / "dist"
