# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E confidence pass for the relay email backend (ADR 054).

The relay backend submits to a provider/smarthost over TLS + SASL, so a full
send→capture would need a STARTTLS+SASL sink — out of scope here. Instead this
validates the part that is Hop3's code:

1. Install Postfix (`--with email` pre-stage).
2. `server email backend relay` (pointed at a local `:587` that is *not* a real
   relay) — drives the rootd `postfix.configure` op + the pm-aware reload.
3. Assert the config Hop3 wrote: `relayhost = [127.0.0.1]:587`, SASL enabled, and
   the credential in `sasl_passwd`.
4. Assert Postfix is listening on `127.0.0.1:25`.
5. Submit a message through `127.0.0.1:25` and assert Postfix **accepts it and
   queues it for relay** — the smarthost is unreachable, so it defers, which
   proves the accept + relay path. (The TLS+SASL wire delivery itself is
   standard Postfix, not Hop3 code.)

Helpers are duplicated from ``test_email_catch.py`` on purpose — c_e2e tests
don't import siblings, and this must not touch the passing catch test.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.e2e

_FROM = "noreply@example.com"
_SUBJECT = "hop3-relay-e2e"
_VENV = "/home/hop3/venv/bin"

_INSTALL_POSTFIX = (
    "command -v postfix >/dev/null 2>&1 || { "
    "echo 'postfix postfix/main_mailer_type select No configuration' "
    "| debconf-set-selections && "
    "DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
    "DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a "
    "apt-get install -y -qq postfix; }"
)


def _sh(target, script: str) -> tuple[int, str, str]:
    """Run a bash snippet in the container as root; return (code, out, err)."""
    return target.exec_run(["bash", "-c", script])


def _extract_token(out: str) -> str:
    for line in out.splitlines():
        s = line.strip()
        if s and " " not in s and len(s) >= 20:
            return s
    return ""


def _bootstrap_admin_token(target) -> str:
    """Create (or reuse) an admin server-side and return its API token."""
    code, out, err = _sh(
        target,
        f"echo e2e-relay-pw | sudo -u hop3 {_VENV}/hop3-server admin:create "
        "relayadmin relayadmin@example.com --password-stdin",
    )
    combined = out + err
    if "already exists" in combined or "already registered" in combined:
        code, out, err = _sh(
            target, f"sudo -u hop3 {_VENV}/hop3-server admin:token relayadmin"
        )
    assert code == 0, f"admin bootstrap failed: {err or out}"
    token = _extract_token(out)
    assert token, f"could not parse an admin token from: {out!r}"
    return token


def _run_admin_cli(target, token: str, *args: str) -> tuple[int, str, str]:
    argstr = " ".join(args)
    return _sh(
        target,
        f"sudo -u hop3 env HOP3_API_URL=http://localhost:8000 "
        f"HOP3_API_TOKEN={token} {_VENV}/hop3 {argstr}",
    )


class TestEmailRelayBackend:
    """The relay backend configures Postfix and queues submitted mail for relay."""

    def test_relay_configures_and_queues(self, deployment_target) -> None:
        target = deployment_target

        code, out, err = _sh(target, _INSTALL_POSTFIX)
        assert code == 0, f"postfix install failed: {err or out}"

        # Select the relay backend, pointed at a local :587 that isn't a real
        # smarthost — enough to exercise the config + queue path.
        token = _bootstrap_admin_token(target)
        code, out, err = _run_admin_cli(
            target,
            token,
            "server", "email", "backend", "relay",
            "--smtp-host", "127.0.0.1", "--smtp-port", "587",
            "--smtp-user", "relayuser", "--smtp-password", "relaypass",
            "--from-domain", "example.com",
        )  # fmt: skip
        combined = f"{out}\n{err}"
        assert "Admin privileges required" not in combined, combined
        assert "ERROR" not in err, f"backend relay errored: {err or out}"

        # The config Hop3 wrote: relayhost + SASL + the stored credential.
        _, main_cf, _ = _sh(target, "cat /etc/postfix/main.cf")
        assert "relayhost = [127.0.0.1]:587" in main_cf
        assert "smtp_sasl_auth_enable = yes" in main_cf
        _, sasl, _ = _sh(target, "cat /etc/postfix/sasl_passwd")
        assert "[127.0.0.1]:587 relayuser:relaypass" in sasl

        # Postfix listening on the loopback submission port.
        code, out, err = _sh(
            target,
            'python3 -c "import socket; '
            "socket.create_connection(('127.0.0.1', 25), timeout=10).close()\"",
        )
        assert code == 0, f"Postfix is not listening on 127.0.0.1:25: {err or out}"

        # Submit through the loopback relay — Postfix accepts and queues it.
        send = (
            "import smtplib, email.message; "
            "m = email.message.EmailMessage(); "
            f"m['From'] = '{_FROM}'; m['To'] = 'dest@example.com'; "
            f"m['Subject'] = '{_SUBJECT}'; m.set_content('hello from hop3'); "
            "s = smtplib.SMTP('127.0.0.1', 25, timeout=15); "
            "s.send_message(m); s.quit()"
        )
        code, out, err = _sh(target, f'python3 -c "{send}"')
        assert code == 0, f"submission to the loopback relay failed: {err or out}"

        # The message must be queued for relay (the smarthost is unreachable, so
        # Postfix defers rather than delivering) — proves accept + relay attempt.
        queued = self._await_queued(target)
        assert "example.com" in queued, f"message was not queued for relay: {queued!r}"

    @staticmethod
    def _await_queued(target, *, attempts: int = 15, delay: float = 1.0) -> str:
        for _ in range(attempts):
            _, out, _ = _sh(
                target, "postqueue -p 2>/dev/null || mailq 2>/dev/null || true"
            )
            if "example.com" in out:
                return out
            time.sleep(delay)
        _, log, _ = _sh(target, "tail -n 40 /var/log/mail.log 2>/dev/null || true")
        msg = f"no message queued for relay after {attempts}s; mail log:\n{log}"
        raise AssertionError(msg)
