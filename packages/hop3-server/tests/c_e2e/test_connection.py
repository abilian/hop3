# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The SSH transport, end to end: the tunnel, the token commands over it, and the
root path into `hop3 app shell`.

``hop3`` reaches an ``ssh://`` server by opening ``ssh -L`` to it and speaking
JSON-RPC through the tunnel; ``hop3 app shell`` is the one command that opens
``ssh -t`` instead. Nothing else in the suite drives either: every other test
talks HTTP to the container's published API port, because the ``hop3`` account's
key carries the forced command and ``no-port-forwarding``. So the e2e image also
authorises the same key for ``root``, plain, which is the production shape (the
operator's key in root's authorized_keys) and the account ``hop3 login``
connects as.

These ran as opt-in "remote diagnostics" before, and so never ran. They still
accept ``--ssh-host HOST`` and then target that box instead of the container
(HOP3_DEV_HOST / HOP3_TEST_HOST are ignored on purpose, ADR 043); the shell test
is container-only, since it deploys an app to open a shell in.

The CLI subprocesses get a private ``HOME``: the tunnel accepts new host keys,
and a container's key must not land in the developer's known_hosts, where a
rebuilt image on a reused port would later read as a changed host.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import tomllib

from .conftest import (
    FLASK_REQUIREMENTS,
    create_flask_app,
    deploy_app_dir,
    init_git_repo,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.e2e]

_USER = "test-diagnostic-user"
_PASSWORD = "test-pass-12345"


@dataclass(frozen=True)
class SshTarget:
    user: str
    host: str
    port: int
    key: str | None  # None: the developer's own keys (a real box)

    @property
    def api_url(self) -> str:
        return f"ssh://{self.user}@{self.host}:{self.port}"

    def ssh_argv(self, *remote: str) -> list[str]:
        argv = [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if self.key:
            argv += ["-i", self.key, "-o", "UserKnownHostsFile=/dev/null"]
        argv += ["-p", str(self.port), f"{self.user}@{self.host}", *remote]
        return argv


@pytest.fixture(scope="class")
def ssh_target(
    request: pytest.FixtureRequest, hop3_container: dict[str, Any]
) -> SshTarget:
    """The explicit ``--ssh-host`` box when given, else the container as root."""
    remote = request.config.getoption("--ssh-host")
    if remote:
        user, _, host = remote.rpartition("@")
        return SshTarget(user=user or "root", host=host, port=22, key=None)
    return SshTarget(
        user="root",
        host=hop3_container["host"],
        port=int(hop3_container["ssh_port"]),
        key=hop3_container["ssh_key"],
    )


def _cli_env(target: SshTarget, home: Path) -> dict[str, str]:
    """
    Point ``hop3`` at the target over ssh://.

    Against the container the CLI gets its own config dir (the login stores a
    token there), the container's key and port, and a private known_hosts, so
    an ephemeral container's host key never lands in the developer's own, where
    a rebuilt image on a reused port would later read as a changed host. ssh
    resolves ``~`` through the passwd entry, not ``$HOME``, so the private file
    goes through ``HOP3_SSH_OPTIONS``, which every ssh the CLI spawns honours.
    Against a real box (``--ssh-host``) the developer's keys and known_hosts
    are exactly what should be used.
    """
    env = os.environ.copy()
    env.pop("HOP3_API_TOKEN", None)
    env["HOP3_API_URL"] = target.api_url
    env["HOP3_NO_INPUT"] = "1"
    if target.key:
        env["HOP3_CONFIG_DIR"] = str(home / "hop3-cli")
        env["HOP3_SSH_KEY"] = target.key
        env["HOP3_SSH_PORT"] = str(target.port)
        env["HOP3_SSH_OPTIONS"] = f"UserKnownHostsFile={home / 'known_hosts'}"
    return env


def _hop3(
    target: SshTarget,
    home: Path,
    *args: str,
    timeout: int = 60,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hop3", *args],
        env=_cli_env(target, home),
        input=input,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class TestSshTransport:
    def test_ssh_reaches_the_target(self, ssh_target: SshTarget) -> None:
        result = subprocess.run(
            ssh_target.ssh_argv("echo", "ok"),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, f"ssh failed: {result.stderr}"
        assert result.stdout.strip() == "ok"

    def test_help_arrives_through_the_tunnel(
        self, ssh_target: SshTarget, tmp_path: Path
    ) -> None:
        """`hop3 help` is a server command: it only answers if the tunnel works."""
        result = _hop3(ssh_target, tmp_path, "help")
        assert result.returncode == 0, f"hop3 help over ssh failed: {result.stderr}"
        assert "auth" in result.stdout, result.stdout[:500]

    def test_login_over_ssh_then_user_add_and_get_token(
        self, ssh_target: SshTarget, tmp_path: Path
    ) -> None:
        """
        The bootstrap, end to end: `hop3 login root@host` mints an admin
        token through `su - hop3 -c "hop3-server admin:ssh-token"` and records
        the server as the default; `user add` (admin-only) and `auth get-token`
        then run against that recorded server with that token, no env override.
        A user left by an earlier run on a real box is fine.
        """
        env = _cli_env(ssh_target, tmp_path)
        del env["HOP3_API_URL"]  # the login must record the server itself

        def hop3(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["hop3", *args],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )

        login = hop3("login", f"{ssh_target.user}@{ssh_target.host}:{ssh_target.port}")
        assert login.returncode == 0, f"login failed: {login.stdout}\n{login.stderr}"

        # A viewer: a member gets no token (ADR 061).
        added = hop3(
            "user", "add", _USER, "test@example.com", _PASSWORD, "--role", "viewer"
        )
        assert (
            added.returncode == 0 or "already exists" in added.stdout + added.stderr
        ), f"user add failed: {added.stdout}\n{added.stderr}"
        got = hop3("auth", "get-token", _USER, _PASSWORD)
        assert got.returncode == 0, f"get-token failed: {got.stdout}\n{got.stderr}"
        jwt = got.stdout.strip().splitlines()[-1]
        assert jwt.count(".") == 2, f"not a JWT: {jwt!r}"

    def test_app_shell_runs_as_hop3_through_root(
        self, hop3_container: dict[str, Any], ssh_target: SshTarget, tmp_path: Path
    ) -> None:
        """
        `hop3 app shell` from a client connected as root: `su - hop3 -c
        hop3-server app-shell`, the production path. Scripted stdin, so no pty.
        """
        if ssh_target.key is None:
            pytest.fail(
                "the shell test deploys into the container; run it without --ssh-host"
            )
        app_dir = create_flask_app(
            tmp_path, "shell-over-ssh", requirements=FLASK_REQUIREMENTS
        )
        init_git_repo(app_dir)
        deployed = deploy_app_dir(hop3_container, app_dir, "shell-over-ssh")
        assert deployed.returncode == 0, deployed.stdout[-800:] + deployed.stderr[-400:]

        result = _hop3(
            ssh_target, tmp_path, "app", "shell", "--app", "shell-over-ssh",
            input="echo APP=$APP; pwd; exit 7\n", timeout=120,
        )  # fmt: skip
        assert result.returncode == 7, result.stdout + result.stderr
        assert "APP=shell-over-ssh" in result.stdout
        assert "/home/hop3/apps/shell-over-ssh/src" in result.stdout


class TestHttpsIsTheEverydayTransport:
    """
    SSH mints the token; it should not also carry every later command.

    A login used to record `ssh://root@host` as the connection, so `hop3 apps`
    and every other read opened a root shell once per invocation. The server is
    now asked for its own public address (`admin:server-url`), and that becomes
    the everyday one.

    The container has no admin domain and no trusted certificate, so what it can
    prove is the *fallback* half and the server-side probe. The trusted-HTTPS
    half is unit-tested (`test_https_transport.py`) and needs a box with a real
    domain — a self-signed container would take the untrusted-certificate branch
    and pass for the wrong reason.
    """

    def _server_url(self, target: SshTarget, admin_domain: str | None = None) -> str:
        """Run `admin:server-url` on the target, optionally overriding the domain."""
        prefix = f"ADMIN_DOMAIN={admin_domain} " if admin_domain is not None else ""
        remote = (
            f"su - hop3 -c '{prefix}/home/hop3/venv/bin/hop3-server admin:server-url'"
        )
        result = subprocess.run(
            target.ssh_argv(remote),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    def test_the_server_reports_no_url_without_an_admin_domain(
        self, ssh_target: SshTarget
    ) -> None:
        """Empty and exit 0 — the answer, not a failure. The client keeps the tunnel."""
        assert self._server_url(ssh_target, admin_domain="") == ""

    def test_the_server_reports_its_url_when_it_has_a_domain(
        self, ssh_target: SshTarget
    ) -> None:
        """Env beats the config file, so this probes without mutating the server."""
        assert (
            self._server_url(ssh_target, admin_domain="hop3.example.com")
            == "https://hop3.example.com"
        )

    def test_login_falls_back_to_the_tunnel_and_says_why(
        self, ssh_target: SshTarget, tmp_path: Path
    ) -> None:
        """
        No admin domain: the SSH tunnel stays, and the operator is told.

        A silent fallback is the failure to avoid — a working CLI whose every
        command opens a root shell the operator never chose.
        """
        env = _cli_env(ssh_target, tmp_path)
        del env["HOP3_API_URL"]  # the login must record the address itself
        result = subprocess.run(
            ["hop3", "login", f"{ssh_target.user}@{ssh_target.host}"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "tunnel over SSH" in result.stderr, result.stderr
        assert "no admin domain" in result.stderr, result.stderr

        config = tomllib.loads((tmp_path / "hop3-cli" / "config.toml").read_text())
        recorded = config["contexts"]["default"]["server"]
        assert recorded.startswith("ssh://"), recorded

    def test_an_expired_token_renews_over_the_bootstrap_route(
        self, ssh_target: SshTarget, tmp_path: Path
    ) -> None:
        """
        Renewal is gated on knowing an SSH route, not on the connection being one.

        Clearing the stored token leaves the context intact; the next command
        must mint a fresh one by itself rather than failing the operator.
        """
        env = _cli_env(ssh_target, tmp_path)
        del env["HOP3_API_URL"]
        login = subprocess.run(
            ["hop3", "login", f"{ssh_target.user}@{ssh_target.host}"],
            env=env, capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip
        assert login.returncode == 0, login.stdout + login.stderr

        credentials = tmp_path / "hop3-cli" / "credentials.toml"
        assert credentials.exists(), "the login stored a token"
        credentials.unlink()

        result = subprocess.run(
            ["hop3", "apps"],
            env=env, capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip
        assert result.returncode == 0, result.stdout + result.stderr
        assert credentials.exists(), "a fresh token was minted and stored"
