# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: the catch email backend captures relayed mail (ADR 054).

Exercises the platform's own path inside the container, with nothing the
platform does not ship:

1. The server is installed `--with email` (the `190-flask-email` fixture
   declares an email addon), which installs Postfix and runs Mailpit.
2. ``hop3 server email backend catch`` — checks Mailpit answers, then drives
   the hop3-rootd ``postfix.configure`` op and the pm-aware reload under
   supervisor (the ``--docker`` target has no systemd).
3. A message relayed through ``127.0.0.1:25`` (what an app with the injected
   ``SMTP_HOST=127.0.0.1`` does) is read back with ``hop3 server email
   caught``, by sender and subject.

It brought its own SMTP sink before: the catch backend relayed to a port
nothing in the platform listened on, and the test could not see it.
"""

from __future__ import annotations

import time

import pytest
from hop3_testing.targets.admin import ensure_admin_token, run_as_admin

pytestmark = pytest.mark.e2e

_FROM = "noreply@hop3.test"
_SUBJECT = "hop3-catch-e2e"


def _sh(target, script: str) -> tuple[int, str, str]:
    """Run a bash snippet in the container as root; return (code, out, err)."""
    return target.exec_run(["bash", "-c", script])


class TestEmailCatchBackend:
    """The catch backend relays app mail to Mailpit (content-checked)."""

    def test_catch_captures_relayed_mail(self, deployment_target) -> None:
        target = deployment_target
        ensure_admin_token(target)

        # Select the catch backend. The CLI exits 0 on an error item, so the
        # effect is checked through status, not the return code.
        _, out, err = run_as_admin(
            target, "server", "email", "backend", "catch", "--from-domain", "hop3.test"
        )
        _, status, _ = run_as_admin(target, "server", "email", "status")
        assert "answering" in status, f"catch not selected: {out}{err}\n{status}"

        # Relay a message through the loopback relay, as an app does.
        send = (
            "import smtplib, email.message; "
            "m = email.message.EmailMessage(); "
            f"m['From'] = '{_FROM}'; m['To'] = 'dest@example.com'; "
            f"m['Subject'] = '{_SUBJECT}'; m.set_content('hello from hop3'); "
            "s = smtplib.SMTP('127.0.0.1', 25, timeout=15); "
            "s.send_message(m); s.quit()"
        )
        code, out, err = _sh(target, f'python3 -c "{send}"')
        assert code == 0, f"sending through the loopback relay failed: {err or out}"

        caught = self._await_caught(target)
        assert _FROM in caught, f"captured mail lacks sender {_FROM!r}: {caught!r}"

    @staticmethod
    def _await_caught(target, *, attempts: int = 20, delay: float = 1.0) -> str:
        """Poll `server email caught` until the message lands (Postfix is async)."""
        listing = ""
        for _ in range(attempts):
            _, listing, _ = run_as_admin(target, "server", "email", "caught")
            if _SUBJECT in listing:
                return listing
            time.sleep(delay)
        _, queue, _ = _sh(target, "postqueue -p 2>&1 | tail -20")
        msg = (
            f"Mailpit captured no {_SUBJECT!r} after {attempts}s; last listing: "
            f"{listing!r}; Postfix queue: {queue!r}"
        )
        raise AssertionError(msg)
