# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The catch backend's sink: Mailpit, on loopback (ADR 054).

`hop3-install server --with email` installs and runs it. The loopback Postfix
relays to its SMTP port when the `catch` backend is selected, and its HTTP API
is how captured mail is read back, by the operator and by the test harness.
"""

from __future__ import annotations

import http.client
import json
import socket
from dataclasses import dataclass

#: Where Mailpit listens; the installer binds these, and hop3-rootd's catch
#: configuration relays to the SMTP one.
SINK_SMTP = ("127.0.0.1", 1025)
SINK_HTTP = ("127.0.0.1", 8025)

_TIMEOUT_S = 5.0

_NOT_RUNNING_HINT = (
    "Mailpit is installed and run by `hop3-install server --with email`; "
    "on a server installed without it, re-run the installer with that flag"
)


class CatcherError(Exception):
    """The catch sink is not answering (the message says where and why)."""


@dataclass(frozen=True)
class CaughtMessage:
    """One message the sink captured."""

    sender: str
    recipients: tuple[str, ...]
    subject: str
    created: str
    snippet: str


def check_sink_answers() -> None:
    """
    Raise unless the sink answers SMTP on its loopback port.

    Selecting the catch backend used to succeed with nothing listening there:
    Postfix then deferred every message, and no mail was ever captured.
    """
    try:
        with socket.create_connection(SINK_SMTP, timeout=_TIMEOUT_S) as sock:
            banner = sock.recv(512).decode("utf-8", "replace")
    except OSError as e:
        msg = f"no email catch sink answers on {SINK_SMTP[0]}:{SINK_SMTP[1]} ({e}). {_NOT_RUNNING_HINT}"
        raise CatcherError(msg) from e
    if not banner.startswith("220"):
        msg = (
            f"{SINK_SMTP[0]}:{SINK_SMTP[1]} answered {banner.strip()!r}, not an "
            f"SMTP greeting. {_NOT_RUNNING_HINT}"
        )
        raise CatcherError(msg)


def caught_messages(limit: int = 50) -> list[CaughtMessage]:
    """The most recent messages the sink captured, newest first."""
    host, port = SINK_HTTP
    path = f"/api/v1/messages?limit={limit}"
    connection = http.client.HTTPConnection(host, port, timeout=_TIMEOUT_S)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
    except OSError as e:
        msg = f"could not read captured mail from {host}:{port} ({e}). {_NOT_RUNNING_HINT}"
        raise CatcherError(msg) from e
    finally:
        connection.close()
    if response.status != 200:
        msg = f"the catch sink answered {response.status} to GET {path}: {body[:200]!r}"
        raise CatcherError(msg)
    payload = json.loads(body)
    return [_message(m) for m in payload.get("messages") or []]


def _message(raw: dict) -> CaughtMessage:
    """
    One API entry. A recipient the headers do not name (envelope only) is
    listed by Mailpit under Bcc, so both lists count.
    """
    people = [*(raw.get("To") or []), *(raw.get("Cc") or []), *(raw.get("Bcc") or [])]
    return CaughtMessage(
        sender=(raw.get("From") or {}).get("Address", ""),
        recipients=tuple(p.get("Address", "") for p in people),
        subject=raw.get("Subject", ""),
        created=raw.get("Created", ""),
        snippet=raw.get("Snippet", ""),
    )
