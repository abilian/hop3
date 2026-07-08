# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Configure the loopback Postfix relay for the active email backend (ADR 054).

Called when the operator selects the relay backend (`hop3 server email backend
relay` / `set`). Drives the hop3-rootd `postfix.configure` op via
``LocalRootdClient`` — the same privileged boundary the nginx proxy plugin
crosses. Skipped in unit/integration tests (no live daemon), run in E2E and
production. A failure is surfaced loud by the caller: the relay must actually be
configured, never a fake success.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from hop3.lib.rootd import LocalRootdClient, RootdError

if TYPE_CHECKING:
    from .email import EmailTransport


class OnRampError(Exception):
    """Configuring the loopback relay failed (surfaced loud by the CLI)."""


def _relay_args(transport: EmailTransport) -> dict[str, object]:
    """The `postfix.configure` args for a relay backend (no From — Postfix
    relays whatever envelope the app presents)."""
    return {
        "relay_host": transport.smtp_host,
        "relay_port": transport.smtp_port,
        "sasl_user": transport.smtp_user,
        "sasl_password": transport.smtp_password,
    }


def configure_relay_backend(transport: EmailTransport) -> str | None:
    """Point the loopback Postfix relay at ``transport`` (a provider/smarthost).

    Returns the reload method, or ``None`` when skipped (unit/integration tests,
    which run without a live daemon). Raises :class:`OnRampError` if hop3-rootd
    is unavailable or the op fails.
    """
    return _configure(_relay_args(transport), "relay")


def configure_catch_backend() -> str | None:
    """Point the loopback Postfix relay at a local dev sink (Mailpit).

    Returns the reload method, or ``None`` when skipped in tests. Raises
    :class:`OnRampError` on failure.
    """
    return _configure({"mode": "catch"}, "catch sink")


def _configure(args: dict[str, object], what: str) -> str | None:
    # Skip in unit/integration tests (no live daemon), but NOT in E2E.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("HOP3_E2E_TEST"):
        return None

    try:
        with LocalRootdClient() as client:
            result = client.call("postfix.configure", args)
        return str(result.get("reloaded", "rootd"))
    except RootdError as e:
        msg = (
            f"could not configure the loopback email {what} via hop3-rootd: {e}. "
            "Is Postfix installed ('hop3-install server --with email') and is "
            "hop3-rootd running?"
        )
        raise OnRampError(msg) from e
