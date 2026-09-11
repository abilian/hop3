# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Just enough FastCGI to ask a php-fpm pool whether it is serving.

Hop3's readiness gate requires evidence that a *worker* answered, not that a
socket is bound — a master process binds its listen socket before forking, so
`connect()` succeeds while every child is dead. For an HTTP backend that
evidence is a status line. php-fpm speaks only FastCGI, so the same evidence
has to be collected in its own protocol, and `ping.path` is where php-fpm
offers it: the reply comes from a pool child, so a master with no working
child does not produce one.

This is a client for that one question. It is not a general FastCGI library
and should not grow into one: if a second caller ever needs FastCGI, that is
the signal to reach for a real implementation.

See notes/readiness-and-non-http-backends.md.
"""

from __future__ import annotations

import socket
import struct

__all__ = ["FCGI_PING_PATH", "fastcgi_ping"]

#: The pool's ping endpoint. php-fpm answers this before any script lookup,
#: so it needs no document root and no application code to be correct.
FCGI_PING_PATH = "/-/hop3-ping"

#: Record header: version, type, request id, content length, padding, reserved.
_HEADER = struct.Struct("!BBHHBB")
_VERSION = 1

_TYPE_BEGIN_REQUEST = 1
_TYPE_END_REQUEST = 3
_TYPE_PARAMS = 4
_TYPE_STDIN = 5
_TYPE_STDOUT = 6

#: We are the web server asking for a response; php-fpm is the responder.
_ROLE_RESPONDER = 1

#: One request per connection, so the id is arbitrary but must not be 0
#: (id 0 is reserved for management records).
_REQUEST_ID = 1

_MAX_RESPONSE_BYTES = 64 * 1024


def fastcgi_ping(host: str, port: int, timeout: float = 3.0) -> bool:
    """
    True if a php-fpm pool child answered a FastCGI request on ``host:port``.

    A bound socket that never replies, a master with no live child, and
    anything that is not speaking FastCGI all return False. So does a refused
    connection: the caller is polling, and "not yet" and "never" are the same
    answer to it.
    """
    request = _ping_request()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            return _response_is_complete(_read_stdout(sock))
    except (OSError, struct.error):
        return False


def _ping_request() -> bytes:
    """The whole request as one buffer: begin, params, empty stdin."""
    begin = struct.pack("!HB5x", _ROLE_RESPONDER, 0)
    params = _encode_params({
        "GATEWAY_INTERFACE": "CGI/1.1",
        "REQUEST_METHOD": "GET",
        "SCRIPT_NAME": FCGI_PING_PATH,
        "SCRIPT_FILENAME": FCGI_PING_PATH,
        "REQUEST_URI": FCGI_PING_PATH,
        "QUERY_STRING": "",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SERVER_SOFTWARE": "hop3",
    })
    return b"".join([
        _record(_TYPE_BEGIN_REQUEST, begin),
        _record(_TYPE_PARAMS, params),
        _record(_TYPE_PARAMS, b""),  # end of params
        _record(_TYPE_STDIN, b""),  # end of (empty) body
    ])


def _record(record_type: int, content: bytes) -> bytes:
    header = _HEADER.pack(_VERSION, record_type, _REQUEST_ID, len(content), 0, 0)
    return header + content


def _encode_params(params: dict[str, str]) -> bytes:
    """Name-value pairs, each length prefixed: one byte under 128, else four."""
    out = bytearray()
    for name, value in params.items():
        for part in (name.encode(), value.encode()):
            out += (
                struct.pack("!B", len(part))
                if len(part) < 128
                else struct.pack("!I", len(part) | 0x80000000)
            )
        out += name.encode() + value.encode()
    return bytes(out)


def _read_stdout(sock: socket.socket) -> bytes:
    """Collect STDOUT content until the responder ends the request."""
    buffer = b""
    stdout = bytearray()
    while len(stdout) < _MAX_RESPONSE_BYTES:
        chunk = sock.recv(4096)
        if not chunk:
            break  # peer closed without ending the request
        buffer += chunk
        while len(buffer) >= _HEADER.size:
            _, record_type, _, length, padding, _ = _HEADER.unpack(
                buffer[: _HEADER.size]
            )
            end = _HEADER.size + length + padding
            if len(buffer) < end:
                break  # record still arriving
            if record_type == _TYPE_STDOUT:
                stdout += buffer[_HEADER.size : _HEADER.size + length]
            buffer = buffer[end:]
            if record_type == _TYPE_END_REQUEST:
                return bytes(stdout)
    return bytes(stdout)


def _response_is_complete(stdout: bytes) -> bool:
    """
    A CGI response carries headers, a blank line, then a body.

    Requiring the separator rules out a child that emitted a partial header
    block and died, which is the shape a crash mid-response takes.
    """
    return b"\r\n\r\n" in stdout or b"\n\n" in stdout
