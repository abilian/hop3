# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo context and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DemoContext:
    """Context for demo execution."""

    # Server connection
    server_ip: str
    ssh_user: str = "root"

    # Admin credentials
    admin_user: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = ""

    # Demo settings
    pause_between_steps: float = 0.5
    skip_install: bool = False
    no_cleanup: bool = False
    use_local_code: bool = False
    verbose: bool = False

    # Paths
    hop3_repo: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.server_ip}"

    @property
    def installer_path(self) -> Path:
        return self.hop3_repo / "installer" / "install-server.py"

    @property
    def packages_path(self) -> Path:
        return self.hop3_repo / "packages"

    @property
    def dist_path(self) -> Path:
        return self.hop3_repo / "dist"
