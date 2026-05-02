# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TC001

"""Daemon introspection ops: handshake, health.

These ops have no side-effects and require no privileges. They exist
to support the wire protocol's version handshake (first message on
every connection) and operator-facing health checks.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from hop3_rootd import PROTOCOL_VERSION, __version__
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request

# --- Daemon-wide singletons used by health() ----------------------------

_started_at: float = time.time()
_last_request_at: float = _started_at
_last_reconcile_at: str | None = None
_errors_last_hour: int = 0  # incremented externally; reset on hour rollover


def mark_request_now() -> None:
    """Called by the dispatcher on every accepted request, before invoking
    the op. Lets `daemon.health()` report a recent-activity timestamp.
    """
    global _last_request_at
    _last_request_at = time.time()


def mark_reconcile_now(iso: str) -> None:
    """Called once during startup reconciliation, with the wall-clock ISO ts."""
    global _last_reconcile_at
    _last_reconcile_at = iso


def increment_error_count() -> None:
    """Called by the dispatcher on each error response."""
    global _errors_last_hour
    _errors_last_hour += 1


def reset_error_count() -> None:
    """Called periodically (or at start-of-hour) to reset the rolling counter."""
    global _errors_last_hour
    _errors_last_hour = 0


# --- Ops -----------------------------------------------------------------


@register("daemon.handshake", audit=False)
def handshake(_req: Request, _ctx: OpContext) -> dict[str, Any]:
    """First message on every connection. Verifies protocol-version compat.

    `_req.v` is already validated against PROTOCOL_VERSION at decode time;
    if we got here, versions match. The optional `client_version` and
    `client_protocol_version` fields in the request are diagnostic only.
    """
    return {
        "daemon_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "accepted": True,
    }


@register("daemon.health", audit=False)
def health(_req: Request, ctx: OpContext) -> dict[str, Any]:
    """Return daemon liveness + summary stats. Read-only, side-effect-free."""
    now = time.time()
    return {
        "daemon_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "uptime_seconds": round(now - _started_at, 3),
        "rules_count": len(ctx.state.rules),
        "last_reconcile_at": _last_reconcile_at,
        "last_request_at": _format_ts(_last_request_at),
        "errors_last_hour": _errors_last_hour,
    }


def _format_ts(epoch: float) -> str:
    """Format a float epoch as ISO-8601 UTC."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
