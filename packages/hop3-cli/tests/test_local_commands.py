# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for local CLI commands (init, config, login --ssh)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pytest
from hop3_cli.config import Config
from hop3_cli.local_commands import (
    BootstrapError,
    config_get,
    config_set,
    config_show,
    extract_token,
    handle_init,
    handle_login_ssh,
    infer_server_url,
    is_local_command,
)
from hop3_cli.rich_printer import RichPrinter


class TestIsLocalCommand:
    """Tests for is_local_command function."""

    def test_empty_args(self):
        """Test with empty arguments."""
        assert is_local_command([]) is False

    def test_init_command(self):
        """Test that init is recognized as local."""
        assert is_local_command(["init"]) is True
        assert is_local_command(["init", "--ssh", "user@host"]) is True

    def test_config_command(self):
        """Test that config is recognized as local."""
        assert is_local_command(["config"]) is True
        assert is_local_command(["config", "show"]) is True

    def test_login_without_ssh(self):
        """Test that login without --ssh is not local."""
        assert is_local_command(["login"]) is False
        assert is_local_command(["login", "user", "pass"]) is False

    def test_login_with_ssh(self):
        """Test that login with --ssh is local."""
        assert is_local_command(["login", "--ssh", "user@host"]) is True

    def test_other_commands(self):
        """Test that other commands are not local."""
        assert is_local_command(["apps"]) is False
        assert is_local_command(["deploy"]) is False
        assert is_local_command(["status"]) is False


class TestExtractToken:
    """Tests for extract_token function."""

    def test_extract_jwt_token(self):
        """Test extracting a JWT token from output."""
        output = """
        Admin user created successfully.
        Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature123
        """
        token = extract_token(output)
        assert token is not None
        assert token.startswith("eyJ")

    def test_no_token_in_output(self):
        """Test when no token is present."""
        output = "No token here"
        assert extract_token(output) is None

    def test_multiple_tokens(self):
        """Test that first token is returned."""
        output = """
        Token 1: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmaXJzdCI6dHJ1ZX0.sig1
        Token 2: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZWNvbmQiOnRydWV9.sig2
        """
        token = extract_token(output)
        assert token is not None
        assert "first" in token or token.startswith("eyJ")


class TestInferServerUrl:
    """Tests for infer_server_url function."""

    def test_user_at_host(self):
        """Test user@host format."""
        assert infer_server_url("root@example.com") == "https://example.com"
        assert infer_server_url("admin@my-server.io") == "https://my-server.io"

    def test_host_only(self):
        """Test host only format."""
        assert infer_server_url("example.com") == "https://example.com"

    def test_with_ssh_port(self):
        """Test with SSH port (should be stripped)."""
        assert infer_server_url("root@example.com:22") == "https://example.com"
        assert infer_server_url("example.com:2222") == "https://example.com"


class TestConfigCommands:
    """Tests for config subcommands."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = Config(data={}, config_file=config_path)
            yield config

    @pytest.fixture
    def mock_printer(self):
        """Create a mock printer."""
        return MagicMock(spec=RichPrinter)

    def test_config_show_empty(self, temp_config, mock_printer, capsys):
        """Test config show with no settings."""
        result = config_show(temp_config, mock_printer)
        assert result is True

        captured = capsys.readouterr()
        assert "No settings configured" in captured.out

    def test_config_show_with_data(self, temp_config, mock_printer, capsys):
        """Test config show with settings."""
        # Use a token longer than 20 chars to trigger masking
        long_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.sig"
        temp_config.data = {"api_url": "https://test.com", "api_token": long_token}

        result = config_show(temp_config, mock_printer)
        assert result is True

        captured = capsys.readouterr()
        assert "api_url = https://test.com" in captured.out
        # Token should be masked (truncated with ...)
        assert "..." in captured.out
        # Full token should not appear
        assert long_token not in captured.out

    def test_config_set(self, temp_config, mock_printer, capsys):
        """Test setting a config value."""
        result = config_set(
            ["api_url", "https://new-server.com"], temp_config, mock_printer
        )
        assert result is True

        # Verify it was saved
        assert temp_config.data["api_url"] == "https://new-server.com"

    def test_config_set_alias(self, temp_config, mock_printer, capsys):
        """Test setting config using alias."""
        result = config_set(
            ["server", "https://alias-test.com"], temp_config, mock_printer
        )
        assert result is True

        # 'server' should be converted to 'api_url'
        assert temp_config.data["api_url"] == "https://alias-test.com"

    def test_config_get(self, temp_config, mock_printer, capsys):
        """Test getting a config value."""
        temp_config.data = {"api_url": "https://test.com"}

        result = config_get(["api_url"], temp_config, mock_printer)
        assert result is True

        captured = capsys.readouterr()
        assert "https://test.com" in captured.out


class TestHandleInit:
    """Tests for handle_init command."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = Config(data={}, config_file=config_path)
            yield config

    @pytest.fixture
    def mock_printer(self):
        """Create a mock printer."""
        return MagicMock(spec=RichPrinter)

    def test_init_help(self, temp_config, mock_printer, capsys):
        """Test init --help shows help."""
        result = handle_init(["--help"], temp_config, mock_printer)
        assert result is True

        captured = capsys.readouterr()
        assert "Usage: hop3 init --ssh" in captured.out

    def test_init_missing_ssh(self, temp_config, mock_printer):
        """Test init without --ssh fails."""
        with pytest.raises(SystemExit) as exc_info:
            handle_init([], temp_config, mock_printer)
        assert exc_info.value.code == 1

    def test_init_success(self, temp_config, mock_printer, capsys):
        """Test successful init via SSH."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature"
        )

        # Mock SSH execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = f"Admin user created.\nToken: {mock_token}"
        mock_result.stderr = ""

        with (
            patch("hop3_cli.local_commands.subprocess.run", return_value=mock_result),
            patch(
                "hop3_cli.local_commands.getpass.getpass",
                side_effect=["pass123", "pass123"],
            ),
            patch("builtins.input", side_effect=["admin", "admin@example.com", ""]),
        ):
            result = handle_init(
                ["--ssh", "root@test.com", "-y"],
                temp_config,
                mock_printer,
            )

        assert result is True
        assert temp_config.data["api_token"] == mock_token
        assert "https://test.com" in temp_config.data["api_url"]


class TestHandleLoginSsh:
    """Tests for handle_login_ssh command."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = Config(data={}, config_file=config_path)
            yield config

    @pytest.fixture
    def mock_printer(self):
        """Create a mock printer."""
        return MagicMock(spec=RichPrinter)

    def test_login_ssh_help(self, temp_config, mock_printer, capsys):
        """Test login --ssh --help shows help."""
        result = handle_login_ssh(
            ["--ssh", "user@host", "--help"], temp_config, mock_printer
        )
        assert result is True

        captured = capsys.readouterr()
        assert "Usage: hop3 login --ssh" in captured.out

    def test_login_ssh_success(self, temp_config, mock_printer, capsys):
        """Test successful login via SSH."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIn0.signature"
        )

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = f"Token generated.\nToken: {mock_token}"
        mock_result.stderr = ""

        with (
            patch("hop3_cli.local_commands.subprocess.run", return_value=mock_result),
            patch(
                "builtins.input", side_effect=["", "testuser"]
            ),  # Server URL default, username
        ):
            result = handle_login_ssh(
                ["--ssh", "root@test.com"],
                temp_config,
                mock_printer,
            )

        assert result is True
        assert temp_config.data["api_token"] == mock_token


class TestBootstrapError:
    """Tests for BootstrapError exception."""

    def test_bootstrap_error_message(self):
        """Test BootstrapError can hold a message."""
        error = BootstrapError("Connection failed")
        assert str(error) == "Connection failed"
