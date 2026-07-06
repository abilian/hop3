# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Platform notifications (EXPERIMENTAL) — email the operator on server events.

Opt-in. When enabled, :func:`notify` delivers a message through the server-level
email transport (see :mod:`.server_transport`) to the operator. Today it carries
cert-renewal-failure alerts; the event set grows with the monitoring roadmap.

:func:`notify` is best-effort and never raises — a notification must not break
the operation it reports on. But it never fails *silently* either: a delivery
failure (or an enabled-but-unconfigured channel) is logged loudly, and
``server email notifications status`` surfaces a misconfiguration where the
operator looks.

The config is a singleton at ``HOP3_ROOT/server/notifications.json`` (0600),
mirroring the email-transport store. The recipient defaults to ``ACME_EMAIL``
(already the operator's address) unless overridden.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hop3.config import HOP3_ROOT, config
from hop3.lib.logging import server_log

from .sender import send_via_transport
from .server_transport import load_server_transport

if TYPE_CHECKING:
    from pathlib import Path


def _store_path() -> Path:
    """Path to the notifications config (call-time for test isolation)."""
    return HOP3_ROOT / "server" / "notifications.json"


def save_notifications_config(*, enabled: bool, recipient: str | None = None) -> None:
    """Persist the opt-in flag and optional recipient override. Idempotent."""
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    record: dict[str, object] = {"enabled": enabled}
    if recipient:
        record["recipient"] = recipient
    path.write_text(json.dumps(record, indent=2))
    path.chmod(0o600)


def load_notifications_config() -> dict:
    """The stored config, or the default (disabled) when unset."""
    path = _store_path()
    if not path.exists():
        return {"enabled": False}
    return json.loads(path.read_text())


def notifications_enabled() -> bool:
    return bool(load_notifications_config().get("enabled"))


def notification_recipient() -> str:
    """The resolved recipient: the explicit override, else ACME_EMAIL, else ''."""
    cfg = load_notifications_config()
    return cfg.get("recipient") or config.ACME_EMAIL or ""


def notify(event: str, subject: str, body: str) -> bool:
    """Deliver an operator notification. Returns True iff it was sent.

    Never raises (a failed alert must not break the reporting operation), but a
    failure — including "enabled but no transport/recipient" and a corrupt config
    store — is logged loudly, never swallowed. A disabled channel is a legitimate
    no-op (the operator opted out), not a failure.

    The pre-flight loads run *inside* the guard too: a corrupt / hand-edited
    ``notifications.json`` or ``email-transport.json`` (bad JSON, or a rejected
    ``smtp_port``) must surface loudly and return False, not raise — the
    cert-renewal cycle that calls this relies on it never raising.
    """
    try:
        if not notifications_enabled():
            return False  # operator opted out — a legitimate no-op

        transport = load_server_transport()
        recipient = notification_recipient()
        if transport is None or not recipient:
            server_log.error(
                "notifications enabled but cannot send",
                event=event,
                reason="no server email transport"
                if transport is None
                else "no recipient",
            )
            return False

        send_via_transport(transport, recipient, subject, body)
    except Exception as exc:  # best-effort channel: surface loudly, then swallow
        server_log.error(
            "notification failed",
            event=event,
            error=str(exc),
        )
        return False
    server_log.info("notification sent", event=event, recipient=recipient)
    return True
