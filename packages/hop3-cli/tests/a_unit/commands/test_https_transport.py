# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
HTTPS is the everyday transport; SSH is bootstrap and rescue.

An SSH login used to record `ssh://root@host` as the connection, so every
later `hop3 apps`, `hop3 logs` and `hop3 status` opened a root shell — far more
privilege than listing apps needs, once per invocation. The server is now asked
for its own public address, and that becomes the everyday one; the SSH target
is kept only as the route a token is minted through.

The tunnel remains the answer when there is no HTTPS endpoint, and the operator
is told why rather than left with a root shell they never chose.
"""

from __future__ import annotations

import subprocess

import pytest
from hop3_cli.commands.local import login_cmd, ssh_ops
from hop3_cli.config import DEFAULT_CONTEXT_NAME, Config

SSH_TARGET = "root@prod.example.com"
PUBLIC = "https://prod.example.com"
TOKEN = "eyJhbGciOi.p.s"


@pytest.fixture
def server_says(monkeypatch):
    """Stub what `admin:server-url` answers, and whether HTTPS is usable."""

    def configure(url: str | None, reason: str = "", https_problem: str = ""):
        monkeypatch.setattr(
            login_cmd, "server_url_and_reason", lambda _t: (url, reason)
        )
        monkeypatch.setattr(
            login_cmd, "_https_unusable_because", lambda *_a: https_problem
        )

    return configure


def determine(config: Config) -> tuple[str, str | None]:
    return login_cmd._determine_save_url(None, SSH_TARGET, TOKEN, config, 0)


class TestWhatGetsRecorded:
    def test_https_becomes_the_everyday_address(self, server_says):
        server_says(PUBLIC)
        server, bootstrap = determine(Config(data={}))
        assert server == PUBLIC
        assert bootstrap == f"ssh://{SSH_TARGET}", "the SSH route is kept, not used"

    def test_no_admin_domain_keeps_the_tunnel(self, server_says, capsys):
        server_says(None, reason="no-admin-domain")
        server, bootstrap = determine(Config(data={}))
        assert server == f"ssh://{SSH_TARGET}"
        assert bootstrap is None, "the server IS the ssh route; no second copy"
        err = capsys.readouterr().err
        assert "tunnel over SSH as root" in err
        assert "no admin domain" in err
        assert "--admin-domain" in err, "names the fix"

    def test_an_untrusted_certificate_keeps_the_tunnel(self, server_says, capsys):
        server_says(
            PUBLIC, https_problem="has a certificate this machine does not trust"
        )
        server, _ = determine(Config(data={}))
        assert server == f"ssh://{SSH_TARGET}"
        assert "certificate" in capsys.readouterr().err

    def test_an_old_server_keeps_the_tunnel_and_says_so(self, server_says, capsys):
        """Absence of `admin:server-url` must fall back cleanly, not fail."""
        server_says(None, reason="outdated-server")
        server, _ = determine(Config(data={}))
        assert server == f"ssh://{SSH_TARGET}"
        err = capsys.readouterr().err
        assert "too old" in err
        assert "no admin domain" not in err, "the wrong diagnosis for this server"

    def test_an_explicit_url_still_wins(self, server_says, monkeypatch):
        """`--url` is the operator's choice; it is not second-guessed."""
        server_says(PUBLIC)
        monkeypatch.setattr(login_cmd, "_verify_https_connection", lambda *a, **k: None)
        server, bootstrap = login_cmd._determine_save_url(
            "https://named.example.com", SSH_TARGET, TOKEN, Config(data={}), 0
        )
        assert server == "https://named.example.com"
        assert bootstrap == f"ssh://{SSH_TARGET}"


class TestBootstrapRoute:
    def test_recorded_alongside_the_server(self, tmp_path):
        config = Config(data={}, config_file=tmp_path / "config.toml")
        config.set_context_server("prod", PUBLIC, bootstrap=f"ssh://{SSH_TARGET}")
        assert config.get_context_server("prod") == PUBLIC
        assert config.get_context_bootstrap("prod") == f"ssh://{SSH_TARGET}"

    def test_an_ssh_server_is_its_own_bootstrap(self, tmp_path):
        config = Config(data={}, config_file=tmp_path / "config.toml")
        config.set_context_server("prod", f"ssh://{SSH_TARGET}")
        assert config.get_context_bootstrap("prod") == f"ssh://{SSH_TARGET}"

    def test_a_later_token_login_does_not_erase_it(self, tmp_path):
        """A password or token login knows no SSH route; it must not drop one."""
        config = Config(data={}, config_file=tmp_path / "config.toml")
        config.set_context_server("prod", PUBLIC, bootstrap=f"ssh://{SSH_TARGET}")
        config.set_context_server("prod", "https://moved.example.com")
        assert config.get_context_bootstrap("prod") == f"ssh://{SSH_TARGET}"


class TestRenewalIsNotGatedOnTheScheme:
    """The bug: `_can_auto_auth` required the CONNECTION to be ssh://."""

    def test_an_https_context_can_still_renew(self):
        config = Config(
            data={
                "contexts": {DEFAULT_CONTEXT_NAME: {"server": PUBLIC}},
                "cli": {"default_context": DEFAULT_CONTEXT_NAME},
            }
        )
        config.set_active_server(PUBLIC)
        config.set_active_bootstrap(f"ssh://{SSH_TARGET}")
        assert config.get_bootstrap_target() == SSH_TARGET

    def test_an_ssh_connection_still_renews_without_a_recorded_route(self):
        config = Config(data={})
        config.set_active_server(f"ssh://{SSH_TARGET}")
        assert config.get_bootstrap_target() == SSH_TARGET

    def test_a_port_survives(self):
        config = Config(data={})
        config.set_active_bootstrap("ssh://root@prod.example.com:2222")
        assert config.get_bootstrap_target() == "root@prod.example.com:2222"

    def test_no_route_means_no_renewal(self):
        config = Config(data={})
        config.set_active_server(PUBLIC)
        assert config.get_bootstrap_target() is None


class TestTheProbe:
    def test_a_url_is_returned(self, monkeypatch):
        monkeypatch.setattr(
            ssh_ops, "_run_ssh", lambda *a, **k: _completed(0, f"{PUBLIC}\n")
        )
        assert ssh_ops.server_url_and_reason(SSH_TARGET) == (PUBLIC, "")

    def test_empty_output_means_no_admin_domain(self, monkeypatch):
        monkeypatch.setattr(ssh_ops, "_run_ssh", lambda *a, **k: _completed(0, "\n"))
        assert ssh_ops.server_url_and_reason(SSH_TARGET) == (None, "no-admin-domain")

    def test_a_nonzero_exit_means_an_old_server(self, monkeypatch):
        monkeypatch.setattr(ssh_ops, "_run_ssh", lambda *a, **k: _completed(2, ""))
        assert ssh_ops.server_url_and_reason(SSH_TARGET) == (None, "outdated-server")


def _completed(returncode: int, stdout: str = ""):
    return subprocess.CompletedProcess(["ssh"], returncode, stdout, "")


class TestTheDashboardLinkWarns:
    """
    `auth:magic-link` returns a bare token exactly when there is no admin domain.

    That is the same condition as "no HTTPS endpoint", and the dashboard's
    session cookie is `Secure` — so the link the CLI is about to build cannot
    hold a session. Handing it over silently leaves the browser to fail with
    nothing explaining why.
    """

    def test_a_bare_token_warns_before_the_link(self, monkeypatch, capsys):
        monkeypatch.setattr(
            login_cmd, "get_magic_link_via_ssh", lambda *_a: "bare-token-no-url"
        )
        monkeypatch.setattr(login_cmd, "_resolved_server_url", lambda _c: None)
        login_cmd.handle_login_web(["--web", SSH_TARGET], Config(data={}), None)

        captured = capsys.readouterr()
        assert "no admin domain" in captured.err
        assert "Secure" in captured.err
        assert "--admin-domain" in captured.err
        assert "bare-token-no-url" in captured.out, "the link is still printed"

    def test_a_full_url_from_the_server_does_not_warn(self, monkeypatch, capsys):
        """A full URL means the server HAS an admin domain; nothing to warn about."""
        monkeypatch.setattr(
            login_cmd,
            "get_magic_link_via_ssh",
            lambda *_a: f"{PUBLIC}/auth/magic/tok",
        )
        login_cmd.handle_login_web(["--web", SSH_TARGET], Config(data={}), None)

        captured = capsys.readouterr()
        assert "no admin domain" not in captured.err
        assert f"{PUBLIC}/auth/magic/tok" in captured.out
