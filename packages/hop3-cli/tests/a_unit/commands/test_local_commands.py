# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for local CLI commands (init, settings, the login bootstrap)."""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import pytest
import requests
from hop3_cli.commands.local import (
    BootstrapError,
    extract_token,
    handle_auth,
    handle_init,
    handle_login,
    handle_login_token,
    handle_logout,
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
from hop3_cli.commands.local.ssh_ops import validate_ssh_target
from hop3_cli.config import DEFAULT_CONTEXT_NAME, Config, get_config
from hop3_cli.core import credential_store as cs
from hop3_cli.exceptions import TargetError
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


@pytest.fixture
def temp_config(tmp_path: Path) -> Config:
    """A real config, written under the test's own directory."""
    return Config(data={}, config_file=tmp_path / "config.toml")


@pytest.fixture
def printer() -> RichPrinter:
    """A real printer: what a command shows is asserted on captured output."""
    return RichPrinter()


@dataclass
class FakeSsh:
    """
    ``subprocess.run`` for the ssh bootstrap: records argv, answers ``stdout``.

    The commands are real; only the process boundary is replaced, so a test
    sees the exact command line the CLI would have run.
    """

    stdout: str
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=self.stdout, stderr="")


@dataclass
class FakeClient:
    """
    The RPC client: answers every call with ``result`` and records the calls.

    Built by the code under test (``Client(config=...)``), so the instance
    keeps the config it was given and ``FakeClient.made`` lists every one.
    """

    result: list[dict]
    made: list[FakeClient] = field(default_factory=list)
    config: Config | None = None
    calls: list[tuple[str, list[str]]] = field(default_factory=list)

    def __call__(self, config: Config, **_kwargs: Any) -> FakeClient:
        client = FakeClient(self.result, config=config)
        self.made.append(client)
        return client

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def rpc(self, method: str, params: list[str]) -> Ok:
        self.calls.append((method, params))
        return Ok(id=1, result=self.result)


def _whoami(name: str) -> FakeClient:
    return FakeClient([{"t": "text", "text": f"Logged in as: {name}"}])


def _scripted(*answers: str):
    """A prompt (``input``, ``getpass``) that answers ``answers`` in order."""
    queue = list(answers)
    return lambda _prompt="": queue.pop(0)


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
        # `auth login` / `auth logout` are the rich local flows...
        assert is_local_command(["auth", "login"]) is True
        assert is_local_command(["auth", "logout"]) is True
        # ...but other auth subcommands go to the server.
        assert is_local_command(["auth", "whoami"]) is False
        assert is_local_command(["auth", "get-token"]) is False


class TestExtractToken:
    """Tests for extract_token function."""

    def test_extract_jwt_token(self):
        """
        Test extracting a JWT token from output.

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
    """
    Regression tests for token-login verification (_verify_token).

    The verify step builds a throwaway Config from the URL+token. It MUST
    use the nested [contexts.*] shape — Config.get_api_url() no longer reads
    a flat top-level "api_url" key, so a flat dict yields api_url=None and
    Client raises CliError, which _verify_token's broad except misreports as
    "Could not connect". That silently broke `hop3 login "<url>?token=..."`
    against healthy servers (the Docker demo login failure).
    """

    def test_verify_token_builds_resolvable_config(self, monkeypatch):
        """The temp Config passed to Client must resolve api_url + token."""
        client = _whoami("alice")
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        username = _verify_token("http://localhost:18000", "tok-123")

        assert username == "alice"
        # The crux: the verify config must be resolvable, not a flat dict.
        (made,) = client.made
        assert made.config.get_api_url() == "http://localhost:18000"
        assert made.config.get_api_token() == "tok-123"
        assert made.calls == [("cli", ["auth", "whoami"])]

    def test_verify_token_sends_the_new_token_not_a_stored_one(self, monkeypatch):
        """
        A stored token for the same server, or one in the environment, does not
        stand in for the token being verified.

        After `hop3-deploy-server --docker --clean`, the store still held the
        previous container's token for http://localhost:8000, signed with a
        key that no longer exists; the check sent it, and the new token was
        refused with "Authentication required" without ever being sent.
        """
        cs.set_token("http://localhost:8000", "stale-token")
        monkeypatch.setenv("HOP3_API_TOKEN", "env-token")
        monkeypatch.setenv("HOP3_API_URL", "http://elsewhere:8000")
        client = _whoami("admin")
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        _verify_token("http://localhost:8000", "new-token")

        (made,) = client.made
        assert made.config.get_api_url() == "http://localhost:8000"
        assert made.config.get_api_token() == "new-token"


@dataclass
class FakeHttp:
    """``requests.get``: raises ``error`` if set, else answers ``status``."""

    status: int = 200
    error: Exception | None = None

    def __call__(self, url: str, **_kwargs: Any) -> requests.Response:
        if self.error is not None:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response.url = url
        return response


class TestVerifyHttpsConnection:
    """
    Regression tests for HTTPS verification during login.

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

    def test_self_signed_cert_aborts_login(self, monkeypatch, capsys):
        error = requests.exceptions.SSLError("self-signed")
        monkeypatch.setattr("requests.get", FakeHttp(error=error))
        with pytest.raises(SystemExit) as exc:
            _verify_https_connection("https://hop3.dev", "tok", self._config(), {})
        assert exc.value.code == ExitCode.AUTH_ERROR
        assert "Refusing to log in" in capsys.readouterr().err

    def test_valid_cert_does_not_abort(self, monkeypatch, capsys):
        monkeypatch.setattr("requests.get", FakeHttp(status=200))
        # Must return normally (no SystemExit) for a trusted cert.
        _verify_https_connection("https://hop3.dev", "tok", self._config(), {})
        assert "HTTPS connection verified" in capsys.readouterr().out


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

    def test_settings_show_empty(self, temp_config, printer, capsys):
        """Test settings show with no settings."""
        settings_show(temp_config, printer)

        captured = capsys.readouterr()
        assert "No settings configured" in captured.out

    def test_settings_show_with_data(self, temp_config, printer, capsys):
        """Test settings show with settings."""
        # Use a token longer than 20 chars to trigger masking
        long_token = _FAKE_JWT_TEST
        temp_config.data = {"api_url": "https://test.com", "api_token": long_token}

        settings_show(temp_config, printer)

        captured = capsys.readouterr()
        assert "api_url = https://test.com" in captured.out
        # Token should be masked (truncated with ...)
        assert "..." in captured.out
        # Full token should not appear
        assert long_token not in captured.out

    def test_settings_set(self, temp_config, printer, capsys):
        """Test setting a settings value."""
        settings_set(["ssl_cert", "/etc/ssl/server.crt"], temp_config, printer)

        # Verify it was saved
        assert temp_config.data["ssl_cert"] == "/etc/ssl/server.crt"

    @pytest.mark.parametrize("key", ["server", "api_url", "token", "api_token"])
    def test_the_server_and_token_are_not_settings(
        self, temp_config, printer, capsys, key
    ):
        """Nothing reads these keys: writing one would only pretend to work."""
        with pytest.raises(SystemExit) as exc:
            settings_set([key, "value"], temp_config, printer)
        assert exc.value.code == ExitCode.USAGE_ERROR
        assert "hop3 " in capsys.readouterr().err
        assert key not in temp_config.data

    def test_settings_set_non_connection_key_does_not_warn(
        self, temp_config, printer, capsys
    ):
        settings_set(["verify_ssl", "false"], temp_config, printer)
        assert "deprecated" not in capsys.readouterr().err.lower()
        assert temp_config.data["verify_ssl"] == "false"

    def test_settings_get(self, temp_config, printer, capsys):
        """Test getting a settings value."""
        temp_config.data = {"api_url": "https://test.com"}

        settings_get(["api_url"], temp_config, printer)

        captured = capsys.readouterr()
        assert "https://test.com" in captured.out


class TestHandleInit:
    """Tests for handle_init command."""

    def test_init_help(self, temp_config, printer, capsys):
        """Test init --help shows help."""
        handle_init(["--help"], temp_config, printer)

        captured = capsys.readouterr()
        assert "Usage: hop3 init --ssh" in captured.out

    def test_init_missing_ssh(self, temp_config, printer, capsys):
        """Init without --ssh is a usage error, exit 2."""
        with pytest.raises(SystemExit) as exc_info:
            handle_init([], temp_config, printer)
        assert exc_info.value.code == ExitCode.USAGE_ERROR
        assert "--ssh is required" in capsys.readouterr().err

    def test_init_success(self, temp_config, printer, monkeypatch):
        """Test successful init via SSH, with every credential prompted."""
        ssh = FakeSsh(f"Admin user created.\nToken: {_FAKE_JWT_ADMIN}")
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)
        monkeypatch.setattr("getpass.getpass", _scripted("pass123", "pass123"))
        monkeypatch.setattr("builtins.input", _scripted("admin", "admin@example.com"))

        handle_init(["--ssh", "root@test.com", "-y"], temp_config, printer)

        # The ssh bootstrap was asked for the admin the prompts named.
        (argv,) = ssh.calls
        assert "root@test.com" in argv
        assert "admin" in argv[-1]
        # ADR 042 r2: token goes to the per-server store, server becomes default.
        assert cs.get_token("https://test.com") == _FAKE_JWT_ADMIN
        assert (
            temp_config.get_context_server(DEFAULT_CONTEXT_NAME) == "https://test.com"
        )
        # The context is written address-only; config.toml stays secret-free.
        assert _FAKE_JWT_ADMIN not in repr(temp_config.data)

    @pytest.mark.parametrize("host", ["hop3.example.com", "host.example.com"])
    def test_init_password_stdin_never_prompts_for_the_server(
        self, temp_config, printer, monkeypatch, host
    ):
        """
        Regression: `hop3 init --ssh <target> --password-stdin` must NOT
        prompt for the server URL — it infers one from the SSH target —
        otherwise the prompt consumes the piped password line, leaving the
        password empty ("Password cannot be empty"). (ADR 042 removed the
        global `--server` override this used to rely on.)
        """
        ssh = FakeSsh(f"Token: {_FAKE_JWT_ADMIN}")
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)
        monkeypatch.setattr("sys.stdin", io.StringIO("s3cret\n"))

        handle_init(
            [
                "--ssh",
                f"root@{host}",
                "--username",
                "admin",
                "--email",
                "admin@example.com",
                "--password-stdin",
            ],
            temp_config,
            printer,
        )

        # The piped password reached the bootstrap, on its stdin (never argv).
        (argv,) = ssh.calls
        assert "s3cret" not in " ".join(argv)
        # URL inferred from the SSH host, not prompted.
        assert temp_config.get_context_server(DEFAULT_CONTEXT_NAME) == f"https://{host}"
        assert cs.get_token(f"https://{host}") == _FAKE_JWT_ADMIN


class TestHandleLogin:
    """Tests for handle_login command."""

    def test_login_help(self, temp_config, printer, capsys):
        """Test login --help shows help."""
        handle_login(["--help"], temp_config, printer)

        captured = capsys.readouterr()
        assert "Usage: hop3 login" in captured.out
        assert "--token -|@<path>" in captured.out

    def test_login_ssh_success(self, temp_config, printer, monkeypatch):
        """Test successful login via SSH."""
        ssh = FakeSsh(f"Token generated.\nToken: {_FAKE_JWT_USER}")
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)

        handle_login(["--ssh", "root@test.com"], temp_config, printer)

        # ADR 042 r2: SSH login stores the token in the per-server store keyed by
        # the SSH-tunnel URL, and sets it as the default server.
        assert cs.get_token("ssh://root@test.com") == _FAKE_JWT_USER
        assert (
            temp_config.get_context_server(DEFAULT_CONTEXT_NAME)
            == "ssh://root@test.com"
        )
        assert _FAKE_JWT_USER not in repr(temp_config.data)

    def test_login_web_invokes_colon_command(self, temp_config, printer, monkeypatch):
        """
        Regression: `hop3 login --browser` must call `hop3-server auth:magic-link`.

        The space form (`auth magic-link`) makes hop3-server parse `auth` as the
        command and fail with "Unknown command 'auth'", breaking web login.
        """
        ssh = FakeSsh(_FAKE_JWT_ADMIN)
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)

        handle_login(["--web", "root@test.com"], temp_config, printer)

        remote_cmd = ssh.calls[0][-1]  # ["ssh", ..., target, remote_cmd]
        assert "auth:magic-link" in remote_cmd
        assert "auth magic-link" not in remote_cmd

    @pytest.mark.parametrize(
        ("target", "link"),
        [
            # A production Hop3 with a domain is TLS-fronted on 443; the old
            # http://{host}:8000 sent the single-use login token in cleartext
            # to the wrong port.
            ("root@test.com", f"https://test.com/auth/magic/{_FAKE_JWT_ADMIN}"),
            # A local dev server has no TLS: keep http://localhost:8000.
            (
                "root@localhost",
                f"http://localhost:8000/auth/magic/{_FAKE_JWT_ADMIN}",
            ),
        ],
    )
    def test_login_web_bare_token_builds_the_link_for_the_host(
        self, temp_config, printer, monkeypatch, capsys, target, link
    ):
        ssh = FakeSsh(_FAKE_JWT_ADMIN)
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)

        handle_login(["--web", target], temp_config, printer)

        out = capsys.readouterr().out
        assert link in out
        assert out.count(":8000") == link.count(":8000")

    def test_login_web_honors_context_override_for_target(
        self, temp_config, printer, monkeypatch, capsys
    ):
        """
        `--context prod login --browser` targets prod, not the default server.

        Regression: `login` dispatches before main wires the active server, so
        the SSH target used to come from the default server, ignoring --context.
        """
        temp_config.set_context_server("prod", "ssh://root@prod.example.com")
        temp_config.set_context_override("prod")
        ssh = FakeSsh(_FAKE_JWT_ADMIN)
        monkeypatch.setattr("hop3_cli.commands.local.ssh_ops.subprocess.run", ssh)

        handle_login(["--web"], temp_config, printer)  # no explicit target

        assert "root@prod.example.com" in ssh.calls[0]
        out = capsys.readouterr().out
        assert f"https://prod.example.com/auth/magic/{_FAKE_JWT_ADMIN}" in out

    def test_login_web_aborts_on_undefined_context(self, temp_config, printer):
        """An explicit --context that names no context fails loud, not silently."""
        temp_config.set_context_override("staging")  # never defined
        with pytest.raises(SystemExit) as exc_info:
            handle_login(["--web"], temp_config, printer)
        assert exc_info.value.code == 1

    def test_login_web_uses_full_url_from_server(
        self, temp_config, printer, monkeypatch, capsys
    ):
        """When the server returns a full URL (admin domain), print it verbatim."""
        full = f"https://admin.example.com/auth/magic/{_FAKE_JWT_ADMIN}"
        monkeypatch.setattr(
            "hop3_cli.commands.local.ssh_ops.subprocess.run", FakeSsh(full)
        )

        handle_login(["--web", "root@test.com"], temp_config, printer)

        assert full in capsys.readouterr().out

    def test_login_password_unconfigured(self, temp_config, printer):
        """Password login with no server refuses, saying how to sign in."""
        with pytest.raises(TargetError, match="no context selected"):
            handle_login([], temp_config, printer)

    def test_auth_login_runs_the_local_login(self, temp_config, printer, capsys):
        """`hop3 auth login ...` runs the rich local handler, not an RPC call."""
        handled = handle_auth(["login", "--help"], temp_config, printer)

        assert handled is True
        assert "Usage: hop3 login" in capsys.readouterr().out

    def test_logout_not_logged_in(self, temp_config, printer, monkeypatch, capsys):
        """Logout with no token just reports it — no server call."""
        client = FakeClient([])
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        handle_logout([], temp_config, printer)

        assert client.made == []
        assert "Not logged in" in capsys.readouterr().out

    def test_logout_revokes_and_clears_token(
        self, temp_config, printer, monkeypatch, capsys
    ):
        """Logout revokes the token server-side and clears it from the store."""
        # The token lives in the per-server store, keyed by the global
        # current context's server.
        temp_config.set_context_server(DEFAULT_CONTEXT_NAME, "https://test.com")
        temp_config.set_default_context(DEFAULT_CONTEXT_NAME)
        cs.set_token("https://test.com", _FAKE_JWT_USER)
        client = FakeClient([])
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        handle_logout([], temp_config, printer)

        assert client.made[0].calls == [("cli", ["auth", "logout"])]
        assert cs.get_token("https://test.com") is None
        assert "Logged out" in capsys.readouterr().out

    def test_logout_after_login_finds_the_server(
        self, temp_config, printer, monkeypatch
    ):
        """
        A login records a default context, which logout must find.

        A login writes `[contexts.default]` and `[cli].default_context`, never
        the retired `default_server`, and `get_api_url` read only the latter:
        logout after any login said "Not logged in" and left the token.
        """
        monkeypatch.setattr("hop3_cli.rpc.Client", _whoami("testuser"))
        handle_login_token(
            ["--token", _FAKE_JWT_TEST, "--url", "https://test.com"],
            temp_config,
            printer,
        )
        # The logout is another process: it reads only what the login saved.
        saved = get_config(temp_config.config_file)
        client = FakeClient([])
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        handle_logout([], saved, printer)

        assert client.made[0].calls == [("cli", ["auth", "logout"])]
        assert cs.get_token("https://test.com") is None

    def test_login_token_success(self, temp_config, printer, monkeypatch, capsys):
        """Test successful token-based login, the token read from a file."""
        (Path.cwd() / "token").write_text(_FAKE_JWT_TEST + "\n")
        client = _whoami("testuser")
        monkeypatch.setattr("hop3_cli.rpc.Client", client)

        handle_login_token(
            ["--token", "@token", "--url", "http://localhost:8000"],
            temp_config,
            printer,
        )

        # The token sent for verification is the one in the file.
        assert client.made[0].config.get_api_token() == _FAKE_JWT_TEST
        # ADR 042 r2: token to the per-server store keyed by the --url server.
        assert cs.get_token("http://localhost:8000") == _FAKE_JWT_TEST
        assert (
            temp_config.get_context_server(DEFAULT_CONTEXT_NAME)
            == "http://localhost:8000"
        )
        assert "Logged in as testuser" in capsys.readouterr().out

    def test_login_token_with_existing_server(self, temp_config, printer, monkeypatch):
        """Test token login uses the existing default server when no --url given."""
        # Pre-configure the global context (no --url on the command line).
        temp_config.set_context_server(
            DEFAULT_CONTEXT_NAME, "https://existing-server.com"
        )
        temp_config.set_default_context(DEFAULT_CONTEXT_NAME)
        monkeypatch.setattr("hop3_cli.rpc.Client", _whoami("testuser"))
        monkeypatch.setattr("sys.stdin", io.StringIO(_FAKE_JWT_TEST))

        handle_login_token(["--token", "-"], temp_config, printer)

        assert cs.get_token("https://existing-server.com") == _FAKE_JWT_TEST
        assert (
            temp_config.get_context_server(DEFAULT_CONTEXT_NAME)
            == "https://existing-server.com"
        )

    def test_login_token_missing_token(self, temp_config, printer, monkeypatch):
        """`--token` with no value and no terminal to prompt on is a usage error."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            handle_login_token(["--token"], temp_config, printer)
        assert exc_info.value.code == ExitCode.USAGE_ERROR

    def test_login_token_verification_fails(self, temp_config, printer, monkeypatch):
        """A token the server refuses is not saved."""

        def refusing_client(config: Config, **_kwargs: Any) -> FakeClient:
            msg = "connection refused"
            raise requests.exceptions.ConnectionError(msg)

        monkeypatch.setattr("hop3_cli.rpc.Client", refusing_client)
        with pytest.raises(SystemExit) as exc_info:
            handle_login_token(
                ["--token", _FAKE_JWT_TEST, "--url", "http://localhost:8000"],
                temp_config,
                printer,
            )
        assert exc_info.value.code == 1

        # Config should NOT be saved (no contexts created)
        assert not temp_config.data.get("contexts")
        assert cs.get_token("http://localhost:8000") is None

    @pytest.mark.parametrize(
        "server",
        ["http://localhost:8000", "https://my-server.com/api"],
    )
    def test_login_url_with_token_is_refused(
        self, temp_config, printer, capsys, server
    ):
        """The old `<url>?token=` form put the secret on argv: refused, not used."""
        with pytest.raises(SystemExit) as exc_info:
            handle_login([f"{server}?token={_FAKE_JWT_TEST}"], temp_config, printer)

        assert exc_info.value.code == ExitCode.USAGE_ERROR
        assert "--token -" in capsys.readouterr().err
        assert cs.get_token(server) is None
        assert not temp_config.data.get("contexts")

    def test_a_malformed_address_is_a_usage_error(self, temp_config, printer):
        """`urlparse` raises on `http://[::1`; that must not be a traceback."""
        with pytest.raises(SystemExit) as exc_info:
            handle_login(["http://[::1"], temp_config, printer)

        assert exc_info.value.code == ExitCode.USAGE_ERROR


class TestHandleVersion:
    """Tests for handle_version command."""

    def test_version_shows_cli_version(self, temp_config, printer, capsys):
        """Test version command shows CLI version."""
        handle_version([], temp_config, printer)

        captured = capsys.readouterr()
        assert "hop3-cli" in captured.out


class TestHandleAuth:
    """Tests for handle_auth command."""

    def test_auth_shows_help(self, temp_config, printer, capsys):
        """Test auth command shows authentication help."""
        handle_auth([], temp_config, printer)

        captured = capsys.readouterr()
        assert "Authentication commands" in captured.out
        assert "auth login" in captured.out
        assert "auth whoami" in captured.out

    def test_auth_with_help_flag(self, temp_config, printer, capsys):
        """Test auth --help shows help."""
        handle_auth(["--help"], temp_config, printer)

        captured = capsys.readouterr()
        assert "Authentication commands" in captured.out


class TestBootstrapError:
    """Tests for BootstrapError exception."""

    def test_bootstrap_error_message(self):
        """Test BootstrapError can hold a message."""
        error = BootstrapError("Connection failed")
        assert str(error) == "Connection failed"


class TestValidateSshTarget:
    """Tests for SSH target validation (audit M1 — option injection)."""

    def test_accepts_plain_targets(self):
        for target in ("root@test.com", "host.example.com", "user@1.2.3.4", "u@h:22"):
            validate_ssh_target(target)  # must not raise

    def test_rejects_option_injection(self):
        # ssh://-oProxyCommand=evil@host parses to this target; a leading '-'
        # would be read by ssh as an option (ProxyCommand RCE).
        for target in ("-oProxyCommand=evil@host", "-lroot", "", "user@-h", "a b@host"):
            with pytest.raises(BootstrapError):
                validate_ssh_target(target)
