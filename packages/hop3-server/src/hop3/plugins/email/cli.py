# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`addon email <verb>` commands — EXPERIMENTAL email (SMTP relay) addon.

`addon email create` configures a relay (the operator's SMTP submission
credentials); `addon email status` shows it. Both print an experimental banner.
Attaching, promoting, listing, and detaching reuse the type-agnostic verbs in
`hop3.commands.services` (`addon attach <name> --app <app> --type email`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._errors import command_context
from hop3.commands._response import error, summary, table, text, warning
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

from . import deliverability
from .deliverability import MISSING, UNKNOWN
from .email import EmailAddon, EmailTransport
from .server_transport import (
    RELAY_BACKEND,
    assert_inherited_backend,
    load_server_backend_kind,
    load_server_dkim_selector,
    resolve_inherited,
)

_TYPE = "email"

_EXPERIMENTAL_MSG = "experimental: this command's surface may change (release-plan-0.7)"

_STATUS_ICON = {"present": "✓", MISSING: "✗", UNKNOWN: "?"}


def _deliverability_items(domain: str, dkim_selector: str | None = None) -> list[dict]:
    """
    Run the SPF/DMARC (and DKIM, when a selector is known) DNS pre-flight.

    Never claims "ready": a missing record is a loud, actionable pending state,
    and an unreachable resolver is reported as unverified (not as "OK"). When
    ``dkim_selector`` is known (from a provider profile or ``--dkim-selector``),
    DKIM is a real checked row; otherwise it stays a guidance row, since the
    ``<selector>._domainkey`` name can't be guessed.
    """
    checks = [deliverability.check_spf(domain), deliverability.check_dmarc(domain)]
    if dkim_selector:
        checks.append(deliverability.check_dkim(domain, dkim_selector))
    rows = [[_STATUS_ICON.get(c.status, "?"), c.label, c.detail] for c in checks]
    if not dkim_selector:
        rows.append([
            "—",
            "DKIM",
            "add your provider's DKIM records (selector from its dashboard)",
        ])
    items: list[dict] = [
        table(headers=["", "Record", "Status / what to publish"], rows=rows)
    ]
    if any(c.status == MISSING for c in checks):
        items.append(
            warning(
                f"deliverability incomplete for {domain}: publish the missing records "
                "above before relying on this addon — unauthenticated mail is rejected "
                "or spam-foldered."
            )
        )
    elif any(c.status == UNKNOWN for c in checks):
        items.append(
            warning(
                f"deliverability unverified for {domain}: no DNS resolver available to "
                "check the records — verify them manually at your provider."
            )
        )
    elif dkim_selector:
        items.append(text(f"SPF, DKIM, and DMARC all found for {domain}."))
    else:
        items.append(
            text(
                f"SPF and DMARC found for {domain}; confirm your provider's DKIM "
                "records are also published."
            )
        )
    return items


@register
@dataclass(frozen=True)
class AddonEmailCreateCmd(Command):
    """
    Configure an email (SMTP relay) addon — EXPERIMENTAL.

    Usage: hop3 addon email create <name> --from <addr> [--smtp-host <h>
               --smtp-user <u> --smtp-password <pw> --smtp-port 587]

    With --smtp-*, this addon uses its own per-app provider. Without them, it
    inherits the server-level transport (`hop3 server email set`) — set once,
    used by every app — provided --from is on the server's verified sending
    domain. A partial --smtp-* (some but not all three creds) is refused.

    Attach it with `hop3 addon attach <name> --app <app> --type email`, which
    injects SMTP_*/EMAIL_*/MAIL_* so stock Django/Flask/Node apps can send mail.

    Keep the password out of your shell history (ADR 036): `--smtp-password
    @<path>` reads it from a file and `--smtp-password -` reads it from stdin.

    Examples:
        # Inherit the server transport (after `hop3 server email set`):
        hop3 addon email create mail --from noreply@example.com
        # Per-app provider:
        hop3 addon email create mail --smtp-host smtp.resend.com \\
            --smtp-user resend --smtp-password @./smtp.secret --from noreply@example.com
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "create")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "smtp_host": {"type": str},
        # str (not int) so a non-numeric value yields a clean message below
        # rather than an unhandled ValueError inside parse_cli_args.
        "smtp_port": {"type": str, "default": "587"},
        "smtp_user": {"type": str},
        "smtp_password": {"type": str},
        "from": {"type": str},
    }

    def call(self, *args: str) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        # Default to "" (not None) so a missing flag is falsy for the checks
        # below and the values type as `Any`, not `Any | None`.
        addon_name = parsed.get("addon_name", "")
        host = parsed.get("smtp_host", "")
        port_raw = parsed.get("smtp_port", "587")
        user = parsed.get("smtp_user", "")
        password = parsed.get("smtp_password", "")
        mail_from = parsed.get("from", "")

        # Any per-app SMTP flag selects the override path (this addon's own
        # provider); none selects the inherit path (the server-level transport).
        # A *partial* override is refused — all three creds, or none. An explicit
        # --smtp-port counts as override intent too, so it is never silently
        # dropped on the inherit path (which uses the server transport's port).
        explicit_port = "--smtp-port" in args or any(
            str(a).startswith("--smtp-port=") for a in args
        )
        override = bool(host or user or password or explicit_port)
        required = [("<name>", addon_name), ("--from", mail_from)]
        if override:
            required += [
                ("--smtp-host", host),
                ("--smtp-user", user),
                ("--smtp-password", password),
            ]
        missing = [flag for flag, val in required if not val]
        if missing:
            return [
                text(
                    "Usage: hop3 addon email create <name> --from <addr> "
                    "[--smtp-host <h> --smtp-user <u> --smtp-password <pw> "
                    "--smtp-port 587]"
                ),
                error(f"missing: {', '.join(missing)}"),
            ]

        try:
            validate_service_name(addon_name)
        except InvalidIdentifierError as exc:
            return [error(str(exc))]

        if override:
            return self._create_own(
                addon_name, host, port_raw, user, password, mail_from
            )
        return self._create_inherited(addon_name, mail_from)

    def _create_own(
        self,
        addon_name: str,
        host: str,
        port_raw: str,
        user: str,
        password: str,
        mail_from: str,
    ) -> list[dict]:
        """Store a per-app transport — this addon's own provider credentials."""
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return [error(f"--smtp-port must be a whole number, got {port_raw!r}")]

        # EmailTransport enforces the submission-port/TLS invariant, the From
        # shape, and control-char rejection at the domain boundary.
        try:
            transport = EmailTransport(
                smtp_host=host,
                smtp_port=port,
                smtp_user=user,
                smtp_password=password,
                mail_from=mail_from,
            )
        except ValueError as exc:
            return [error(str(exc))]

        with command_context(
            "configuring email addon", addon_name=addon_name, service_type=_TYPE
        ):
            EmailAddon(addon_name=addon_name).configure(transport)

        return self._created_ok(
            addon_name, mail_from, f"relay via {host}:{port}, from {mail_from}"
        )

    def _create_inherited(self, addon_name: str, mail_from: str) -> list[dict]:
        """Store an addon that inherits the server-level backend."""
        # Validate against the active backend (any kind); fails loud if none is
        # set or the From is off the verified domain.
        try:
            assert_inherited_backend(mail_from)
        except (RuntimeError, ValueError) as exc:
            return [error(str(exc))]

        with command_context(
            "configuring email addon", addon_name=addon_name, service_type=_TYPE
        ):
            EmailAddon(addon_name=addon_name).configure_inherited(mail_from)

        if load_server_backend_kind() == RELAY_BACKEND:
            # An inheriting app sends on the server's verified domain, so its
            # DKIM status is the server transport's — surface it if known.
            transport = resolve_inherited(mail_from)
            return self._created_ok(
                addon_name,
                mail_from,
                f"inheriting the server relay ({transport.smtp_host}:"
                f"{transport.smtp_port}), from {mail_from}",
                dkim_selector=load_server_dkim_selector(),
            )

        # catch (dev sink): mail is captured, not sent — no deliverability check.
        kind = load_server_backend_kind()
        return [
            warning(_EXPERIMENTAL_MSG),
            text(
                f"Email addon '{addon_name}' configured (inheriting the {kind} "
                "backend — a dev sink; mail is captured, not sent)."
            ),
            text(
                f"\nAttach it to an app:\n  hop3 addon attach {addon_name} "
                "--app <app> --type email"
            ),
            summary(f"configured email addon '{addon_name}'."),
        ]

    def _created_ok(
        self,
        addon_name: str,
        mail_from: str,
        detail: str,
        dkim_selector: str | None = None,
    ) -> list[dict]:
        domain = mail_from.rsplit("@", maxsplit=1)[-1]
        return [
            warning(_EXPERIMENTAL_MSG),
            text(f"Email addon '{addon_name}' configured ({detail})."),
            text(
                f"\nAttach it to an app:\n  hop3 addon attach {addon_name} "
                "--app <app> --type email"
            ),
            *_deliverability_items(domain, dkim_selector),
            summary(f"configured email addon '{addon_name}'."),
        ]


@register
@dataclass(frozen=True)
class AddonEmailStatusCmd(Command):
    """
    Show an email addon's relay configuration — EXPERIMENTAL.

    Usage: hop3 addon email status <name>

    Examples:
        hop3 addon email status mail
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "status")
    requires_auth: ClassVar[bool] = True

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon email status <name>")]
        addon_name = args[0]
        with command_context(
            "reading email addon", addon_name=addon_name, service_type=_TYPE
        ):
            info = EmailAddon(addon_name=addon_name).info()

        if not info.get("configured"):
            return [
                warning(_EXPERIMENTAL_MSG),
                warning(f"Email addon '{addon_name}' is not configured."),
                text(
                    f"Configure it: hop3 addon email create {addon_name} "
                    "--smtp-host <h> --smtp-user <u> --smtp-password <pw> --from <addr>"
                ),
            ]

        # An addon that inherits the server transport can resolve to an error
        # (the server transport was removed or its domain changed): surface it
        # loudly rather than crash on the absent transport fields.
        if info.get("error"):
            return [
                warning(_EXPERIMENTAL_MSG),
                warning(
                    f"Email addon '{addon_name}' inherits the server transport, "
                    "which is currently unavailable:"
                ),
                error(info["error"]),
            ]

        domain = info["mail_from"].rsplit("@", 1)[-1]
        rows = [
            ["host", info["smtp_host"]],
            ["port", info["smtp_port"]],
            ["from", info["mail_from"]],
        ]
        # An inherited addon sends on the server domain, so its DKIM status is
        # the server transport's — check it the same way create and `server
        # email status` do, rather than showing a stale guidance row.
        selector = load_server_dkim_selector() if info.get("inherited") else None
        return [
            warning(_EXPERIMENTAL_MSG),
            table(headers=["Field", "Value"], rows=rows),
            *_deliverability_items(domain, selector),
        ]


# Contributed to the RPC dispatch table via EmailPlugin.cli_commands().
@register
class AddonEmailCmd(NamespaceCommand):
    """
    Email (SMTP relay) addon operations (EXPERIMENTAL).

    Configure and inspect an app's outbound email relay. Set it up with
    'hop3 addon email create <name>', then check it with
    'hop3 addon email status <name>'.

    Examples:
        hop3 addon email create myrelay     # Configure an SMTP relay addon
        hop3 addon email status myrelay     # Show the relay configuration
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE)


COMMANDS: list[type[Command]] = [
    AddonEmailCmd,
    AddonEmailCreateCmd,
    AddonEmailStatusCmd,
]
