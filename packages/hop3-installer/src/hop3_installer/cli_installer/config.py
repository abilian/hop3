# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for CLI installer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import env_bool, env_path, env_str

# Package configuration
PACKAGE_NAME = "hop3-cli"
GIT_REPO = "https://github.com/abilian/hop3.git"
GIT_SUBDIR = "packages/hop3-cli"
DEFAULT_BRANCH = "main"

# Installation paths
INSTALL_DIR = Path.home() / ".hop3-cli"
VENV_DIR = INSTALL_DIR / "venv"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"

# Commands to install
CLI_COMMANDS = ["hop3", "hop"]

# Shell configuration files
SHELL_CONFIGS = {
    "bash": Path.home() / ".bashrc",
    "zsh": Path.home() / ".zshrc",
    "fish": Path.home() / ".config" / "fish" / "config.fish",
}


@dataclass
class CLIInstallerConfig:
    """Configuration for CLI installer."""

    # Installation source
    version: str | None = None
    use_git: bool = False
    branch: str = DEFAULT_BRANCH
    local_path: str | None = None

    # Installation options
    bin_dir: Path = field(default_factory=lambda: DEFAULT_BIN_DIR)
    force: bool = False
    no_modify_path: bool = False
    verbose: bool = False

    @classmethod
    def from_env(cls) -> CLIInstallerConfig:
        """Create config from environment variables."""
        return cls(
            version=env_str("HOP3_VERSION"),
            use_git=env_bool("HOP3_GIT"),
            branch=env_str("HOP3_BRANCH", DEFAULT_BRANCH),
            local_path=env_str("HOP3_LOCAL_PACKAGE"),
            bin_dir=env_path("HOP3_BIN_DIR", DEFAULT_BIN_DIR),
            force=env_bool("HOP3_FORCE"),
            no_modify_path=env_bool("HOP3_NO_MODIFY_PATH"),
            verbose=env_bool("HOP3_VERBOSE"),
        )
