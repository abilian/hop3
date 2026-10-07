# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Mailpit is reported running when it answers, and installed only as pinned.

"Mailpit running" was printed on the restart's exit code: a `Type=simple`
unit and `supervisorctl update` both succeed once the process is launched,
before it listens, and nothing checked the port afterwards.
"""

from __future__ import annotations

import io
import socket
import tarfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import mailpit


def _greeter(greeting: bytes) -> tuple[str, threading.Thread]:
    """A one-shot TCP server on loopback that sends ``greeting``."""
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def serve() -> None:
        with server:
            conn, _ = server.accept()
            with conn:
                conn.sendall(greeting)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return f"127.0.0.1:{port}", thread


def test_an_smtp_greeting_is_running():
    address, thread = _greeter(b"220 mailpit ESMTP\r\n")
    with patch.object(mailpit, "MAILPIT_SMTP", address):
        mailpit._await_mailpit_smtp()
    thread.join(timeout=2)


def test_nothing_listening_stops_the_install():
    with socket.create_server(("127.0.0.1", 0)) as probe:
        free_port = probe.getsockname()[1]
    with (
        patch.object(mailpit, "MAILPIT_SMTP", f"127.0.0.1:{free_port}"),
        patch.object(mailpit, "_MAILPIT_WAIT_ATTEMPTS", 2),
        patch.object(mailpit.time, "sleep"),
        pytest.raises(InstallStepError, match="does not answer"),
    ):
        mailpit._await_mailpit_smtp()


def test_an_archive_without_the_binary_is_refused():
    """A missing member raised KeyError, which the installer did not catch."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("README.md")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"hi"))
    archive = buffer.getvalue()

    def fake_curl(cmd, **_kw):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(archive)

    arch = mailpit._mailpit_arch()
    with (
        patch.object(mailpit, "run_cmd", side_effect=fake_curl),
        patch.dict(
            mailpit.MAILPIT_SHA256, {arch: mailpit.hashlib.sha256(archive).hexdigest()}
        ),
        pytest.raises(InstallStepError, match="has no `mailpit` file"),
    ):
        mailpit._install_mailpit_binary()
