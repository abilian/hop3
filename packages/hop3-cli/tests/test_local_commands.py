# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for local CLI commands (init, settings, login --ssh)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pytest
from hop3_cli.commands.local import (
    BootstrapError,
    extract_token,
    handle_auth,
    handle_init,
    handle_login,
    handle_login_token,
    handle_version,
    infer_server_url,
    is_local_command,
    settings_get,
    settings_set,
    settings_show,
)
from hop3_cli.config import Config
from hop3_cli.ui.rich_printer import RichPrinter


class TestIsLocalCommand:
    """Tests for is_local_command function."""

    def test_empty_args(self):
        """Test with empty arguments."""
        assert is_local_command([]) is False

    def test_init_command(self):
        """Test that init is recognized as local."""
        assert is_local_command(["init"]) is True
        assert is_local_command(["init", "--ssh", "user@host"]) is True

    def test_settings_command(self):
        """Test that settings is recognized as local."""
        assert is_local_command(["settings"]) is True
        assert is_local_command(["settings", "show"]) is True

    def test_login_command(self):
        """Test that login is recognized as local (all forms)."""
        assert is_local_command(["login"]) is True
        assert is_local_command(["login", "--ssh", "user@host"]) is True
        assert is_local_command(["login", "--username", "admin"]) is True

    def test_version_command(self):
        """Test that version commands are recognized as local."""
        assert is_local_command(["version"]) is True
        assert is_local_command(["--version"]) is True
        assert is_local_command(["-V"]) is True

    def test_auth_command(self):
        """Test that auth (group help) is recognized as local."""
        assert is_local_command(["auth"]) is True

    def test_other_commands(self):
        """Test that other commands are not local."""
        assert is_local_command(["apps"]) is False
        assert is_local_command(["deploy"]) is False
        assert is_local_command(["status"]) is False
        # auth:* subcommands should go to server
        assert is_local_command(["auth", "login"]) is False
        assert is_local_command(["auth", "whoami"]) is False


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


class TestSettingsCommands:
    """Tests for settings subcommands."""

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

    def test_settings_show_empty(self, temp_config, mock_printer, capsys):
        """Test settings show with no settings."""
        settings_show(temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "No settings configured" in captured.out

    def test_settings_show_with_data(self, temp_config, mock_printer, capsys):
        """Test settings show with settings."""
        # Use a token longer than 20 chars to trigger masking
        long_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.sig"
        temp_config.data = {"api_url": "https://test.com", "api_token": long_token}

        settings_show(temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "api_url = https://test.com" in captured.out
        # Token should be masked (truncated with ...)
        assert "..." in captured.out
        # Full token should not appear
        assert long_token not in captured.out

    def test_settings_set(self, temp_config, mock_printer, capsys):
        """Test setting a settings value."""
        settings_set(["api_url", "https://new-server.com"], temp_config, mock_printer)

        # Verify it was saved
        assert temp_config.data["api_url"] == "https://new-server.com"

    def test_settings_set_alias(self, temp_config, mock_printer, capsys):
        """Test setting settings using alias."""
        settings_set(["server", "https://alias-test.com"], temp_config, mock_printer)

        # 'server' should be converted to 'api_url'
        assert temp_config.data["api_url"] == "https://alias-test.com"

    def test_settings_get(self, temp_config, mock_printer, capsys):
        """Test getting a settings value."""
        temp_config.data = {"api_url": "https://test.com"}

        settings_get(["api_url"], temp_config, mock_printer)

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
        handle_init(["--help"], temp_config, mock_printer)

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
            patch(
                "hop3_cli.commands.local.ssh_ops.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "hop3_cli.commands.local.init_cmd.getpass.getpass",
                side_effect=["pass123", "pass123"],
            ),
            patch("builtins.input", side_effect=["admin", "admin@example.com", ""]),
        ):
            handle_init(
                ["--ssh", "root@test.com", "-y"],
                temp_config,
                mock_printer,
            )

        # Credentials are saved to a "default" context when no context exists
        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token
        assert "https://test.com" in default_ctx["api_url"]


class TestHandleLogin:
    """Tests for handle_login command."""

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

    def test_login_help(self, temp_config, mock_printer, capsys):
        """Test login --help shows help."""
        handle_login(["--help"], temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "Usage: hop3 login" in captured.out
        assert "--ssh" in captured.out

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
            patch(
                "hop3_cli.commands.local.ssh_ops.subprocess.run",
                return_value=mock_result,
            ),
            patch("builtins.input", return_value="testuser"),  # username
        ):
            handle_login(
                ["--ssh", "root@test.com"],
                temp_config,
                mock_printer,
            )

        # Credentials are saved to a "default" context when no context exists
        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token

    def test_login_password_unconfigured(self, temp_config, mock_printer):
        """Test password login fails when server not configured."""
        # Config is empty, so server is not configured
        with pytest.raises(SystemExit) as exc_info:
            handle_login([], temp_config, mock_printer)
        assert exc_info.value.code == 1

    def test_login_token_success(self, temp_config, mock_printer, capsys):
        """Test successful token-based login."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        )

        with patch(
            "hop3_cli.commands.local.login_cmd._verify_token", return_value="testuser"
        ):
            handle_login_token(
                ["--token", mock_token, "--server", "http://localhost:8000"],
                temp_config,
                mock_printer,
            )

        # Credentials are saved to a "default" context when no context exists
        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token
        assert default_ctx["api_url"] == "http://localhost:8000"

    def test_login_token_with_existing_server(self, temp_config, mock_printer, capsys):
        """Test token login uses existing server config."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        )
        # Pre-configure server with existing context
        temp_config.data["contexts"] = {
            "default": {"api_url": "https://existing-server.com", "api_token": ""}
        }
        temp_config.data["current_context"] = "default"

        with patch(
            "hop3_cli.commands.local.login_cmd._verify_token", return_value="testuser"
        ):
            handle_login_token(
                ["--token", mock_token],
                temp_config,
                mock_printer,
            )

        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token
        assert default_ctx["api_url"] == "https://existing-server.com"

    def test_login_token_missing_token(self, temp_config, mock_printer):
        """Test token login fails when token not provided."""
        with pytest.raises(SystemExit) as exc_info:
            handle_login_token(["--token"], temp_config, mock_printer)
        assert exc_info.value.code == 1

    def test_login_token_verification_fails(self, temp_config, mock_printer):
        """Test token login fails when verification fails."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        )

        with patch(
            "hop3_cli.commands.local.login_cmd._verify_token", return_value=None
        ):
            with pytest.raises(SystemExit) as exc_info:
                handle_login_token(
                    ["--token", mock_token, "--server", "http://localhost:8000"],
                    temp_config,
                    mock_printer,
                )
            assert exc_info.value.code == 1

        # Config should NOT be saved (no contexts created)
        assert "contexts" not in temp_config.data or not temp_config.data.get(
            "contexts"
        )

    def test_login_url_with_token(self, temp_config, mock_printer, capsys):
        """Test login with URL containing embedded token."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        )
        url_with_token = f"http://localhost:8000?token={mock_token}"

        with patch(
            "hop3_cli.commands.local.login_cmd._verify_token", return_value="testuser"
        ):
            handle_login([url_with_token], temp_config, mock_printer)

        # Credentials are saved to a "default" context when no context exists
        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token
        assert default_ctx["api_url"] == "http://localhost:8000"

    def test_login_url_with_token_and_path(self, temp_config, mock_printer, capsys):
        """Test login with URL containing path and embedded token."""
        mock_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        )
        url_with_token = f"https://my-server.com/api?token={mock_token}"

        with patch(
            "hop3_cli.commands.local.login_cmd._verify_token", return_value="testuser"
        ):
            handle_login([url_with_token], temp_config, mock_printer)

        # Credentials are saved to a "default" context when no context exists
        default_ctx = temp_config.data["contexts"]["default"]
        assert default_ctx["api_token"] == mock_token
        assert default_ctx["api_url"] == "https://my-server.com/api"


class TestHandleVersion:
    """Tests for handle_version command."""

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

    def test_version_shows_cli_version(self, temp_config, mock_printer, capsys):
        """Test version command shows CLI version."""
        handle_version([], temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "hop3-cli" in captured.out


class TestHandleAuth:
    """Tests for handle_auth command."""

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

    def test_auth_shows_help(self, temp_config, mock_printer, capsys):
        """Test auth command shows authentication help."""
        handle_auth([], temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "Authentication commands" in captured.out
        assert "auth login" in captured.out
        assert "auth register" in captured.out

    def test_auth_with_help_flag(self, temp_config, mock_printer, capsys):
        """Test auth --help shows help."""
        handle_auth(["--help"], temp_config, mock_printer)

        captured = capsys.readouterr()
        assert "Authentication commands" in captured.out


class TestBootstrapError:
    """Tests for BootstrapError exception."""

    def test_bootstrap_error_message(self):
        """Test BootstrapError can hold a message."""
        error = BootstrapError("Connection failed")
        assert str(error) == "Connection failed"
