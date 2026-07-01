# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.cli_installer.config module."""

from __future__ import annotations

from pathlib import Path

from hop3_installer.cli_installer.config import CLIInstallerConfig
from hop3_installer.constants import (
    CLI_COMMANDS,
    CLI_DEFAULT_BIN_DIR,
    DEFAULT_BRANCH_PRODUCTION,
)

# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_cli_commands_contains_expected(self):
        """CLI_COMMANDS should contain hop3 and hop."""
        assert "hop3" in CLI_COMMANDS
        assert "hop" in CLI_COMMANDS

    def test_default_bin_dir_is_local_bin(self):
        """CLI_DEFAULT_BIN_DIR should be ~/.local/bin."""
        assert Path.home() / ".local" / "bin" == CLI_DEFAULT_BIN_DIR

    def test_default_branch(self):
        """DEFAULT_BRANCH_PRODUCTION should be main."""
        assert DEFAULT_BRANCH_PRODUCTION == "main"


# =============================================================================
# CLIInstallerConfig Tests
# =============================================================================


class TestCLIInstallerConfig:
    """Tests for CLIInstallerConfig dataclass."""

    def test_default_values(self):
        """CLIInstallerConfig should have sensible defaults."""
        config = CLIInstallerConfig()

        assert config.version is None
        assert config.use_git is False
        assert config.branch == DEFAULT_BRANCH_PRODUCTION
        assert config.local_path is None
        assert config.bin_dir == CLI_DEFAULT_BIN_DIR
        assert config.force is False
        assert config.no_modify_path is False
        assert config.verbose is False

    def test_custom_values(self):
        """CLIInstallerConfig should accept custom values."""
        config = CLIInstallerConfig(
            version="1.0.0",
            use_git=True,
            branch="develop",
            local_path="/tmp/hop3",
            bin_dir=Path("/usr/local/bin"),
            force=True,
            no_modify_path=True,
            verbose=True,
        )

        assert config.version == "1.0.0"
        assert config.use_git is True
        assert config.branch == "develop"
        assert config.local_path == "/tmp/hop3"
        assert config.bin_dir == Path("/usr/local/bin")
        assert config.force is True
        assert config.no_modify_path is True
        assert config.verbose is True


class TestCLIInstallerConfigFromEnv:
    """Tests for CLIInstallerConfig.from_env()."""

    def test_from_env_defaults(self, clean_env):
        """from_env() should use defaults when no env vars set."""
        config = CLIInstallerConfig.from_env()

        assert config.version is None
        assert config.use_git is False
        assert config.branch == DEFAULT_BRANCH_PRODUCTION
        assert config.force is False

    def test_from_env_version(self, clean_env):
        """from_env() should read HOP3_VERSION."""
        clean_env["HOP3_VERSION"] = "2.0.0"
        config = CLIInstallerConfig.from_env()
        assert config.version == "2.0.0"

    def test_from_env_git_true(self, clean_env):
        """from_env() should parse HOP3_GIT=1 as True."""
        clean_env["HOP3_GIT"] = "1"
        config = CLIInstallerConfig.from_env()
        assert config.use_git is True

    def test_from_env_git_true_lowercase(self, clean_env):
        """from_env() should parse HOP3_GIT=true as True."""
        clean_env["HOP3_GIT"] = "true"
        config = CLIInstallerConfig.from_env()
        assert config.use_git is True

    def test_from_env_git_false(self, clean_env):
        """from_env() should parse other values as False."""
        clean_env["HOP3_GIT"] = "no"
        config = CLIInstallerConfig.from_env()
        assert config.use_git is False

    def test_from_env_branch(self, clean_env):
        """from_env() should read HOP3_BRANCH."""
        clean_env["HOP3_BRANCH"] = "feature-x"
        config = CLIInstallerConfig.from_env()
        assert config.branch == "feature-x"

    def test_from_env_local_path(self, clean_env):
        """from_env() should read HOP3_LOCAL_PACKAGE."""
        clean_env["HOP3_LOCAL_PACKAGE"] = "/path/to/package"
        config = CLIInstallerConfig.from_env()
        assert config.local_path == "/path/to/package"

    def test_from_env_bin_dir(self, clean_env):
        """from_env() should read HOP3_BIN_DIR."""
        clean_env["HOP3_BIN_DIR"] = "/opt/bin"
        config = CLIInstallerConfig.from_env()
        assert config.bin_dir == Path("/opt/bin")

    def test_from_env_force(self, clean_env):
        """from_env() should read HOP3_FORCE."""
        clean_env["HOP3_FORCE"] = "TRUE"
        config = CLIInstallerConfig.from_env()
        assert config.force is True

    def test_from_env_no_modify_path(self, clean_env):
        """from_env() should read HOP3_NO_MODIFY_PATH."""
        clean_env["HOP3_NO_MODIFY_PATH"] = "1"
        config = CLIInstallerConfig.from_env()
        assert config.no_modify_path is True

    def test_from_env_verbose(self, clean_env):
        """from_env() should read HOP3_VERBOSE."""
        clean_env["HOP3_VERBOSE"] = "true"
        config = CLIInstallerConfig.from_env()
        assert config.verbose is True


class TestCleanReinstall:
    """`--clean` is the canonical reinstall flag; `--force` stays an alias (D6)."""

    def test_clean_sets_force(self, clean_env):
        from hop3_installer.cli_installer.cli import (  # noqa: PLC0415
            config_from_args,
            create_parser,
        )

        cfg = config_from_args(create_parser().parse_args(["--clean"]))
        assert cfg.force is True

    def test_force_alias_still_accepted(self, clean_env):
        from hop3_installer.cli_installer.cli import (  # noqa: PLC0415
            config_from_args,
            create_parser,
        )

        cfg = config_from_args(create_parser().parse_args(["--force"]))
        assert cfg.force is True
