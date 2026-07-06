# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`server email notifications <on|off|status|test>` — EXPERIMENTAL.

Opt-in operator alerts (cert-renewal failures for now) delivered through the
server email transport. Admin-only. See :mod:`.notifications`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hop3.commands._base import Command
from hop3.commands._response import error, summary, table, text, warning
from hop3.commands.user import require_admin
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

# Runtime import for Dishka DI (not just a type hint).
from hop3.orm.repositories import UserRepository  # noqa: TC001

from .cli import _EXPERIMENTAL_MSG
from .notifications import (
    load_notifications_config,
    notification_recipient,
    save_notifications_config,
)
from .sender import send_via_transport
from .server_transport import load_server_transport


@register
@dataclass(frozen=True)
class ServerEmailNotificationsCmd(Command):
    """Operator email notifications (cert-renewal alerts) — EXPERIMENTAL.

    Usage: hop3 server email notifications <on|off|status|test> [--to <addr>]

    `on` enables alerts (recipient defaults to your ACME email; override with
    --to). `off` disables them. `status` shows the setting and whether the
    channel is actually deliverable. `test` sends a test message now. Delivered
    through the server email transport (`hop3 server email set`). Admin-only.
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("server", "email", "notifications")
    pass_username: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "action": {"positional": True},
        "to": {"type": str},
    }

    def call(self, authenticated_username: str = "", *args: str) -> list[dict]:
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        parsed = parse_cli_args(args, self._arg_spec)
        action = parsed.get("action", "")
        recipient = parsed.get("to", "")

        handlers = {
            "on": lambda: self._on(recipient),
            "off": self._off,
            "status": self._status,
            "test": lambda: self._test(recipient),
        }
        handler = handlers.get(action)
        if handler is None:
            return [
                text(
                    "Usage: hop3 server email notifications "
                    "<on|off|status|test> [--to <addr>]"
                ),
                error(
                    f"unknown action {action!r}"
                    if action
                    else "missing action: on | off | status | test"
                ),
            ]
        return handler()

    def _on(self, recipient: str) -> list[dict]:
        save_notifications_config(enabled=True, recipient=recipient or None)
        items = [warning(_EXPERIMENTAL_MSG), text("Notifications enabled.")]
        # Pre-flight: surface a misconfiguration where the operator looks, rather
        # than silently enabling a channel that can never deliver.
        resolved = notification_recipient()
        if load_server_transport() is None:
            items.append(
                warning(
                    "No server email transport is set — alerts will NOT send "
                    "until you run `hop3 server email set`."
                )
            )
        elif not resolved:
            items.append(
                warning(
                    "No recipient — pass --to <addr> or set an ACME email; "
                    "alerts will NOT send."
                )
            )
        else:
            items.append(text(f"Alerts will go to {resolved}."))
        items.append(summary("notifications enabled."))
        return items

    def _off(self) -> list[dict]:
        save_notifications_config(enabled=False)
        return [
            warning(_EXPERIMENTAL_MSG),
            text("Notifications disabled."),
            summary("notifications disabled."),
        ]

    def _status(self) -> list[dict]:
        cfg = load_notifications_config()
        enabled = bool(cfg.get("enabled"))
        resolved = notification_recipient()
        transport = load_server_transport()
        rows = [
            ["enabled", "yes" if enabled else "no"],
            ["recipient", resolved or "(none)"],
            ["transport", "set" if transport is not None else "not set"],
        ]
        items = [
            warning(_EXPERIMENTAL_MSG),
            table(headers=["Field", "Value"], rows=rows),
        ]
        if enabled and (transport is None or not resolved):
            why = (
                "set a transport with `hop3 server email set`"
                if transport is None
                else "no recipient (--to / ACME email)"
            )
            items.append(warning(f"Notifications are ON but not deliverable — {why}."))
        return items

    def _test(self, recipient_override: str) -> list[dict]:
        transport = load_server_transport()
        recipient = recipient_override or notification_recipient()
        if transport is None:
            return [
                error(
                    "No server email transport set. Run `hop3 server email set` first."
                )
            ]
        if not recipient:
            return [error("No recipient. Pass --to <addr> or set an ACME email.")]
        try:
            send_via_transport(
                transport,
                recipient,
                "[Hop3] test notification",
                "This is a test notification from Hop3. If you received it, "
                "operator alerts are deliverable.",
            )
        except Exception as exc:  # surface the failure to the operator
            return [error(f"Test send failed: {exc}")]
        return [
            warning(_EXPERIMENTAL_MSG),
            text(f"Test notification sent to {recipient}."),
            summary("sent test notification."),
        ]


# Contributed to the RPC dispatch table via EmailPlugin.cli_commands().
NOTIFY_COMMANDS: list[type[Command]] = [ServerEmailNotificationsCmd]
