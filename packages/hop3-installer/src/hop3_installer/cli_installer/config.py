# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for CLI installer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 - needed at runtime for bundled installer

from hop3_installer.common import env_bool, env_path, env_str
from hop3_installer.constants import (
    CLI_DEFAULT_BIN_DIR,
    DEFAULT_BRANCH_PRODUCTION,
)
from hop3_installer.deprecation import env_bool_with_alias


@dataclass
class CLIInstallerConfig:
    """Configuration for CLI installer."""

    # Installation source
    version: str | None = None
    use_git: bool = False
    branch: str = DEFAULT_BRANCH_PRODUCTION
    local_path: str | None = None

    # Installation options
    bin_dir: Path = field(default_factory=lambda: CLI_DEFAULT_BIN_DIR)
    force: bool = False
    no_modify_path: bool = False
    verbose: bool = False

    @classmethod
    def from_env(cls) -> CLIInstallerConfig:
        """Create config from environment variables."""
        return cls(
            version=env_str("HOP3_VERSION"),
            use_git=env_bool("HOP3_GIT"),
            branch=env_str("HOP3_BRANCH", DEFAULT_BRANCH_PRODUCTION),
            local_path=env_str("HOP3_LOCAL_PACKAGE"),
            bin_dir=env_path("HOP3_BIN_DIR", CLI_DEFAULT_BIN_DIR),
            force=env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE"),
            no_modify_path=env_bool("HOP3_NO_MODIFY_PATH"),
            verbose=env_bool("HOP3_VERBOSE"),
        )
