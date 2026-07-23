# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: the catch email backend captures relayed mail (ADR 054).

Exercises the real platform path inside the container:

1. Install Postfix (the ``--with email`` pre-stage; the e2e image lacks it).
2. ``hop3 server email backend catch`` — drives the hop3-rootd
   ``postfix.configure`` op *and the pm-aware reload under supervisor* (the
   ``--docker`` target has no systemd, so this is the real test of the reload
   fix), configuring the loopback Postfix to relay to a local sink.
3. Assert Postfix is listening on ``127.0.0.1:25``.
4. Relay a message through ``127.0.0.1:25`` (what an app with the injected
   ``SMTP_HOST=127.0.0.1`` does) and assert the sink captured it with the
   sender's From.

The sink is a tiny stdlib SMTP responder written into the container (base64 to
dodge all shell-quoting); the send is a one-shot ``smtplib`` call, standing in
for a deployed app so the test stays self-contained.
"""

from __future__ import annotations

import base64
import textwrap
import time

import pytest

pytestmark = pytest.mark.e2e

_FROM = "noreply@example.com"
_SUBJECT = "hop3-catch-e2e"
_SINK_OUT = "/tmp/hop3-mail-sink.eml"
_SINK_PORT = 1025

# A minimal, correct SMTP sink: accept one message on 127.0.0.1:1025 and write
# it to _SINK_OUT. Single-line 250 EHLO reply → Postfix won't pipeline/STARTTLS
# (the catch main.cf sets smtp_tls_security_level=none anyway).
_SINK_SCRIPT = textwrap.dedent(
    f"""
    import socket
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", {_SINK_PORT}))
    srv.listen(1)
    conn, _ = srv.accept()
    rfile = conn.makefile("rb")

    def reply(s):
        conn.sendall((s + "\\r\\n").encode())

    reply("220 hop3 sink ready")
    lines = []
    in_data = False
    for raw in rfile:
        if in_data:
            text = raw.decode("utf-8", "replace")
            if text.rstrip("\\r\\n") == ".":
                reply("250 queued")
                in_data = False
                continue
            if text.startswith(".."):
                text = text[1:]
            lines.append(text)
            continue
        up = raw.decode("utf-8", "replace").strip().upper()
        if up.startswith(("EHLO", "HELO")):
            reply("250 hop3-sink")
        elif up.startswith("DATA"):
            reply("354 end data with <CR><LF>.<CR><LF>")
            in_data = True
        elif up.startswith("QUIT"):
            reply("221 bye")
            break
        else:
            reply("250 ok")
    with open("{_SINK_OUT}", "w", encoding="utf-8") as out:
        out.write("".join(lines))
    conn.close()
    """
).strip()

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


def _put_file(target, path: str, content: str) -> None:
    """Write ``content`` to ``path`` in the container (base64 — no quoting woes)."""
    b64 = base64.b64encode(content.encode()).decode()
    code, out, err = _sh(target, f"echo {b64} | base64 -d > {path}")
    assert code == 0, f"could not write {path}: {err or out}"


# The DockerTarget mints a *non-admin* CLI token, but `server email backend` is
# admin-gated. Bootstrap a real admin server-side (no RPC auth needed) and run
# the admin command with that token.
_VENV = "/home/hop3/venv/bin"


def _extract_token(out: str) -> str:
    """The API token is the single long, space-free line the admin CLI prints."""
    for line in out.splitlines():
        s = line.strip()
        if s and " " not in s and len(s) >= 20:
            return s
    return ""


def _bootstrap_admin_token(target) -> str:
    """Create (or reuse) an admin user server-side and return its API token."""
    code, out, err = _sh(
        target,
        f"echo e2e-catch-pw | sudo -u hop3 {_VENV}/hop3-server admin:create "
        "catchadmin catchadmin@example.com --password-stdin",
    )
    combined = out + err
    if "already exists" in combined or "already registered" in combined:
        code, out, err = _sh(
            target, f"sudo -u hop3 {_VENV}/hop3-server admin:token catchadmin"
        )
    assert code == 0, f"admin bootstrap failed: {err or out}"
    token = _extract_token(out)
    assert token, f"could not parse an admin token from: {out!r}"
    return token


def _run_admin_cli(target, token: str, *args: str) -> tuple[int, str, str]:
    """Run the hop3 CLI in-container authenticated as the bootstrapped admin."""
    argstr = " ".join(args)
    return _sh(
        target,
        f"sudo -u hop3 env HOP3_API_URL=http://localhost:8000 "
        f"HOP3_API_TOKEN={token} {_VENV}/hop3 {argstr}",
    )


class TestEmailCatchBackend:
    """The catch backend relays app mail to a local sink (content-checked)."""

    def test_catch_captures_relayed_mail(self, deployment_target) -> None:
        target = deployment_target

        # 1. Pre-stage Postfix (the image doesn't ship it).
        code, out, err = _sh(target, _INSTALL_POSTFIX)
        assert code == 0, f"postfix install failed: {err or out}"

        # 2. Start the local SMTP sink before configuring the backend.
        _put_file(target, "/tmp/hop3_sink.py", _SINK_SCRIPT)
        _sh(target, f"rm -f {_SINK_OUT}")
        _sh(target, "nohup python3 /tmp/hop3_sink.py >/tmp/hop3_sink.log 2>&1 &")

        # 3. Select the catch backend as an admin — this runs the rootd
        #    postfix.configure op and the pm-aware reload under supervisor (the
        #    real test of both). The CLI exits 0 even on an error item, so assert
        #    on content, not the return code.
        token = _bootstrap_admin_token(target)
        code, out, err = _run_admin_cli(
            target,
            token,
            "server",
            "email",
            "backend",
            "catch",
            "--from-domain",
            "example.com",
        )
        combined = f"{out}\n{err}"
        assert "Admin privileges required" not in combined, combined
        assert "ERROR" not in err, f"backend catch errored: {err or out}"
        assert "catch" in combined.lower(), f"unexpected backend output: {combined!r}"

        # 4. Postfix must actually be listening on the loopback submission port
        #    (a direct connect — no dependency on `ss`/`netstat` being present).
        code, out, err = _sh(
            target,
            'python3 -c "import socket; '
            "socket.create_connection(('127.0.0.1', 25), timeout=10).close()\"",
        )
        assert code == 0, f"Postfix is not listening on 127.0.0.1:25: {err or out}"

        # 5. Relay a message through 127.0.0.1:25 (what an app with the injected
        #    SMTP_HOST=127.0.0.1 does) and let Postfix deliver it to the sink.
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

        # 6. Postfix delivers asynchronously — poll the sink capture.
        captured = self._await_capture(target)
        assert _FROM in captured, (
            f"captured mail missing sender {_FROM!r}: {captured!r}"
        )
        assert _SUBJECT in captured, f"captured mail missing subject: {captured!r}"

    @staticmethod
    def _await_capture(target, *, attempts: int = 20, delay: float = 1.0) -> str:
        """Poll the sink output file until the relayed message lands (or give up)."""
        for _ in range(attempts):
            _, out, _ = _sh(target, f"cat {_SINK_OUT} 2>/dev/null || true")
            if out.strip():
                return out
            time.sleep(delay)
        # Surface the sink log to make a failure diagnosable.
        _, log, _ = _sh(target, "cat /tmp/hop3_sink.log 2>/dev/null || true")
        msg = f"the catch sink captured no mail after {attempts}s; sink log: {log!r}"
        raise AssertionError(msg)
