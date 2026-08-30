# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The progress body must stay a faithful request body.

Streaming it is only acceptable if `requests` still measures it and sends the
same bytes: a body that fell back to chunked transfer encoding, or that lost a
byte, would trade a silent upload for a broken one.
"""

from __future__ import annotations

import socketserver
import threading

import requests
from hop3_cli.ui.upload_progress import (
    MIN_BODY_BYTES_FOR_PROGRESS,
    ProgressBody,
    upload_body,
)

PAYLOAD = b'{"jsonrpc": "2.0", "params": {"repository": "' + b"x" * 100_000 + b'"}}'


def test_progress_body_keeps_content_length_not_chunked() -> None:
    prepared = requests.Request(
        "POST", "http://localhost:1/rpc", data=ProgressBody(PAYLOAD, lambda _n: None)
    ).prepare()
    assert prepared.headers["Content-Length"] == str(len(PAYLOAD))
    assert "Transfer-Encoding" not in prepared.headers


def test_progress_body_yields_the_same_bytes_and_counts_them() -> None:
    sent: list[int] = []
    body = ProgressBody(PAYLOAD, sent.append)
    assert b"".join(iter(lambda: body.read(4096), b"")) == PAYLOAD
    assert sum(sent) == len(PAYLOAD)


def test_small_body_is_passed_through_untouched() -> None:
    with upload_body(b"tiny") as payload:
        assert payload == b"tiny"


def test_large_body_is_passed_through_when_stderr_is_not_a_tty() -> None:
    """Under pytest stderr is captured: a bar there is noise, not information."""
    big = b"x" * (MIN_BODY_BYTES_FOR_PROGRESS + 1)
    with upload_body(big) as payload:
        assert payload == big


def test_large_body_on_a_tty_reports_progress(monkeypatch) -> None:
    monkeypatch.setattr("sys.stderr.isatty", lambda: True, raising=False)
    big = b"x" * (MIN_BODY_BYTES_FOR_PROGRESS + 1)
    with upload_body(big) as payload:
        assert isinstance(payload, ProgressBody)
        assert payload.read() == big


def test_requests_pulls_the_body_in_chunks_so_the_bar_moves() -> None:
    """
    The whole point is progress *during* the send.

    If `requests` slurped the body in one read the bar would jump 0 -> 100% and
    report nothing, so assert the transport pulls it incrementally — and that
    every byte still arrives. A requests/urllib3 upgrade that buffers the body
    would leave the upload silent again, with the bar as the only clue.
    """
    received: list[bytes] = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            headers: dict[str, str] = {}
            self.rfile.readline()  # request line
            while (line := self.rfile.readline()) not in {b"\r\n", b""}:
                name, _, value = line.decode().partition(":")
                headers[name.lower()] = value.strip()
            received.append(self.rfile.read(int(headers["content-length"])))
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    reads: list[int] = []
    response = requests.post(
        f"http://127.0.0.1:{server.server_address[1]}/rpc",
        data=ProgressBody(PAYLOAD, reads.append),
        timeout=10,
    )
    server.server_close()

    assert response.status_code == 200
    assert received == [PAYLOAD]
    assert len(reads) > 2, f"body was pulled in {len(reads)} read(s), no progress"
