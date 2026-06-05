# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for local CLI commands (init, settings, login --ssh)."""

from __future__ import annotations

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
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
from hop3_cli.commands.local.login_cmd import (
    _verify_https_connection,
    _verify_token,
)
from hop3_cli.config import Config
from hop3_cli.exit_codes import ExitCode
from hop3_cli.ui.rich_printer import RichPrinter
from jsonrpcclient import Ok

# Realistic-shape JWT fixtures: header + payload + 44-char signature.
# Lengths chosen to satisfy the {20,500}-per-segment redaction regex
# in hop3_cli.tokens (real HS256 tokens have 36/40+/43 chars).
_JWT_HEADER = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
_JWT_SIG = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789aBcDeFgH"
_FAKE_JWT_TEST = (
    f"{_JWT_HEADER}.eyJzdWIiOiJ0ZXN0Iiwicm9sZSI6ImFkbWluIiwiaWF0IjoxNzAwMDB9.{_JWT_SIG}"
)
_FAKE_JWT_ADMIN = (
    f"{_JWT_HEADER}.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTcwMDB9.{_JWT_SIG}"
)
_FAKE_JWT_USER = (
    f"{_JWT_HEADER}.eyJzdWIiOiJ1c2VyIiwicm9sZSI6InVzZXIiLCJpYXQiOjE3MDAwMH0.{_JWT_SIG}"
)


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
        """Test extracting a JWT token from output.

        Token shape mirrors a real HS256 token: ~36-char header (the
        canonical ``{"alg":"HS256","typ":"JWT"}``), a payload with
        enough claims to base64-encode past 20 chars, and a 43-char
        signature (HMAC-SHA256 → 256 bits → 43 base64url chars).
        """
        output = """
        Admin user created successfully.
        Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0Iiwicm9sZSI6ImFkbWluIn0.AbCdEfGhIjKlMnOpQrStUvWxYz0123456789aBcDeFgH
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
        # Synthetic but realistic-length tokens — the redaction regex
        # rejects short eyJ.eyJ.X patterns to avoid false positives in
        # log output, so test fixtures need realistic segments.
        sig1 = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789aBcDeFgH"  # 44 chars
        sig2 = "ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210ZyXwVuTs"
        output = f"""
        Token 1: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmaXJzdCI6dHJ1ZSwicm9sZSI6ImEifQ.{sig1}
        Token 2: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZWNvbmQiOnRydWUsInJvbGUiOiJiIn0.{sig2}
        """
        token = extract_token(output)
        assert token is not None
        assert sig1 in token  # first token wins


class TestVerifyToken:
    """Regression tests for token-login verification (_verify_token).

    The verify step builds a throwaway Config from the URL+token. It MUST
    use the nested [contexts.*] shape — Config.get_api_url() no longer reads
    a flat top-level "api_url" key, so a flat dict yields api_url=None and
    Client raises CliError, which _verify_token's broad except misreports as
    "Could not connect". That silently broke `hop3 login "<url>?token=..."`
    against healthy servers (the Docker demo login failure).
    """

    def test_verify_token_builds_resolvable_config(self):
        """The temp Config passed to Client must resolve api_url + token."""
        captured: dict = {}

        class _FakeClient:
            def __init__(self, config, **_kwargs):
                captured["config"] = config

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def rpc(self, _method, _params):
                return Ok(id=1, result=[{"t": "text", "text": "Logged in as: alice"}])

        with patch("hop3_cli.rpc.Client", _FakeClient):
            username = _verify_token("http://localhost:18000", "tok-123")

        assert username == "alice"
        # The crux: the verify config must be resolvable, not a flat dict.
        cfg = captured["config"]
        assert cfg.get_api_url() == "http://localhost:18000"
        assert cfg.get_api_token() == "tok-123"


class TestVerifyHttpsConnection:
    """Regression tests for HTTPS verification during login.

    A self-signed/untrusted cert must ABORT the login. Previously it printed
    "Refusing to log in" but returned normally, so the caller still persisted
    the https URL — producing a self-contradictory flow ("Refusing..." then
    "Credentials saved") and a config that failed SSL verification on every
    subsequent call.
    """

    def _config(self) -> Config:
        return Config(
            data={"contexts": {"default": {}}, "current_context": "default"},
            config_file=None,
        )

    def test_self_signed_cert_aborts_login(self):
        with (
            patch(
                "requests.get",
                side_effect=requests.exceptions.SSLError("self-signed"),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _verify_https_connection("https://hop3.dev", "tok", self._config(), {})
        assert exc.value.code == ExitCode.AUTH_ERROR

    def test_valid_cert_does_not_abort(self):
        ok = Mock()
        ok.ok = True
        ok.status_code = 200
        with patch("requests.get", return_value=ok):
            # Must return normally (no SystemExit) for a trusted cert.
            _verify_https_connection("https://hop3.dev", "tok", self._config(), {})


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
        long_token = _FAKE_JWT_TEST
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
        mock_token = _FAKE_JWT_ADMIN

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

    def test_init_password_stdin_reads_server_from_global_override(
        self, temp_config, mock_printer
    ):
        """Regression: `hop3 init --server <url> --password-stdin`.

        The global flag parser consumes --server before init runs, so init must
        read it from the config override and must NOT prompt for the server URL
        — otherwise that prompt consumes the piped password line, leaving the
        password empty ("Password cannot be empty").
        """
        captured = {}

        def fake_create(ssh_target, username, email, password):
            captured["password"] = password
            return _FAKE_JWT_ADMIN

        # Simulate parse_flags having stashed the stripped `--server <url>`.
        temp_config.set_server_override("https://hop3.example.com")

        with (
            patch(
                "hop3_cli.commands.local.init_cmd.create_admin_via_ssh",
                side_effect=fake_create,
            ),
            patch(
                "hop3_cli.commands.local.init_cmd.sys.stdin", io.StringIO("s3cret\n")
            ),
        ):
            handle_init(
                [
                    "--ssh",
                    "root@hop3.example.com",
                    "--username",
                    "admin",
                    "--email",
                    "admin@example.com",
                    "--password-stdin",
                ],
                temp_config,
                mock_printer,
            )

        assert captured["password"] == "s3cret"
        assert (
            temp_config.data["contexts"]["default"]["api_url"]
            == "https://hop3.example.com"
        )

    def test_init_password_stdin_does_not_prompt_when_no_server(
        self, temp_config, mock_printer
    ):
        """With --password-stdin and no server, infer silently — never prompt.

        A non-tty stdin carries the password; an interactive Server URL prompt
        would eat it. The server URL is inferred from the SSH target instead.
        """
        captured = {}

        def fake_create(ssh_target, username, email, password):
            captured["password"] = password
            return _FAKE_JWT_ADMIN

        with (
            patch(
                "hop3_cli.commands.local.init_cmd.create_admin_via_ssh",
                side_effect=fake_create,
            ),
            patch("hop3_cli.commands.local.init_cmd.sys.stdin", io.StringIO("pw42\n")),
        ):
            handle_init(
                [
                    "--ssh",
                    "root@host.example.com",
                    "--username",
                    "admin",
                    "--email",
                    "admin@example.com",
                    "--password-stdin",
                ],
                temp_config,
                mock_printer,
            )

        assert captured["password"] == "pw42"
        # URL inferred from the SSH host, not prompted.
        assert "host.example.com" in temp_config.data["contexts"]["default"]["api_url"]


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
        mock_token = _FAKE_JWT_USER

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
        mock_token = _FAKE_JWT_TEST

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
        mock_token = _FAKE_JWT_TEST
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
        mock_token = _FAKE_JWT_TEST

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
        mock_token = _FAKE_JWT_TEST
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
        mock_token = _FAKE_JWT_TEST
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
