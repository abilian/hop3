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
    hostname: str
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
    verbose: bool = False
    debug: bool = False  # Maximum verbosity (--debug flag to hop3)
    output_level: OutputLevel = OutputLevel.NORMAL

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
