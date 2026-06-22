# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon email <verb>` commands — EXPERIMENTAL email (SMTP relay) addon.

`addon email create` configures a relay (the operator's SMTP submission
credentials); `addon email status` shows it. Both print an experimental banner.
Attaching, promoting, listing, and detaching reuse the type-agnostic verbs in
`hop3.commands.services` (`addon attach <name> --app <app> --type email`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import error, summary, table, text, warning
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

from . import deliverability
from .deliverability import MISSING, UNKNOWN
from .email import EmailAddon, EmailTransport

_TYPE = "email"

_EXPERIMENTAL_MSG = "experimental: this command's surface may change (release-plan-0.7)"

_STATUS_ICON = {"present": "✓", MISSING: "✗", UNKNOWN: "?"}


def _deliverability_items(domain: str) -> list[dict]:
    """Run the SPF/DMARC DNS pre-flight for `domain` and render it.

    Never claims "ready": a missing record is a loud, actionable pending state,
    and an unreachable resolver is reported as unverified (not as "OK").
    """
    checks = [deliverability.check_spf(domain), deliverability.check_dmarc(domain)]
    rows = [[_STATUS_ICON.get(c.status, "?"), c.label, c.detail] for c in checks]
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
                "check SPF/DMARC — verify them manually at your provider."
            )
        )
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
    """Configure an email (SMTP relay) addon — EXPERIMENTAL.

    Usage: hop3 addon email create <name> --smtp-host <h> --smtp-user <u>
               --smtp-password <pw> --from <addr> [--smtp-port 587]

    Stores the operator's upstream SMTP submission credentials (any provider).
    Attach it with `hop3 addon attach <name> --app <app> --type email`, which
    injects SMTP_*/EMAIL_*/MAIL_* so stock Django/Flask/Node apps can send mail.

    Keep the password out of your shell history (ADR 036): `--smtp-password
    @<path>` reads it from a file and `--smtp-password -` reads it from stdin.

    Examples:
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

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        # Default to "" (not None) so a missing flag is falsy for the check below
        # and the values type as `Any`, not `Any | None`, for the typed calls.
        addon_name = parsed.get("addon_name", "")
        host = parsed.get("smtp_host", "")
        port_raw = parsed.get("smtp_port", "587")
        user = parsed.get("smtp_user", "")
        password = parsed.get("smtp_password", "")
        mail_from = parsed.get("from", "")

        missing = [
            flag
            for flag, val in (
                ("<name>", addon_name),
                ("--smtp-host", host),
                ("--smtp-user", user),
                ("--smtp-password", password),
                ("--from", mail_from),
            )
            if not val
        ]
        if missing:
            return [
                text(
                    "Usage: hop3 addon email create <name> --smtp-host <h> "
                    "--smtp-user <u> --smtp-password <pw> --from <addr> "
                    "[--smtp-port 587]"
                ),
                error(f"missing: {', '.join(missing)}"),
            ]

        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return [error(f"--smtp-port must be a whole number, got {port_raw!r}")]

        try:
            validate_service_name(addon_name)
        except InvalidIdentifierError as exc:
            return [error(str(exc))]

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

        domain = mail_from.split("@")[-1]
        return [
            warning(_EXPERIMENTAL_MSG),
            text(
                f"Email addon '{addon_name}' configured "
                f"(relay via {host}:{port}, from {mail_from})."
            ),
            text(
                f"\nAttach it to an app:\n  hop3 addon attach {addon_name} "
                "--app <app> --type email"
            ),
            *_deliverability_items(domain),
            summary(f"configured email addon '{addon_name}'."),
        ]


@register
@dataclass(frozen=True)
class AddonEmailStatusCmd(Command):
    """Show an email addon's relay configuration — EXPERIMENTAL.

    Usage: hop3 addon email status <name>

    Examples:
        hop3 addon email status mail
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "status")
    requires_auth: ClassVar[bool] = True

    def call(self, *args):
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

        domain = info["mail_from"].split("@")[-1]
        rows = [
            ["host", info["smtp_host"]],
            ["port", info["smtp_port"]],
            ["from", info["mail_from"]],
        ]
        return [
            warning(_EXPERIMENTAL_MSG),
            table(headers=["Field", "Value"], rows=rows),
            *_deliverability_items(domain),
        ]


# Contributed to the RPC dispatch table via EmailPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonEmailCreateCmd,
    AddonEmailStatusCmd,
]
