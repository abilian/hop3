# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`server email <verb>` commands — server-level shared email transport.

The operator sets the SMTP submission credentials once
(`hop3 server email set`); per-app email addons created without their own
`--smtp-*` inherit them. Both commands are admin-only and print an experimental
banner. The per-app `addon email <verb>` commands live in ``cli.py``.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import error, summary, table, text, warning
from hop3.commands.user import require_admin
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

# Runtime import for Dishka DI (not just a type hint).
from hop3.orm.repositories import (
    UserRepository,  # ruff:ignore[typing-only-first-party-import]
)

from .cli import _EXPERIMENTAL_MSG, _deliverability_items
from .email import EmailTransport
from .onramp import (
    OnRampError,
    configure_catch_backend,
    configure_direct_backend,
    configure_relay_backend,
)
from .providers import ProviderProfile, get_provider, list_providers, provider_names
from .server_transport import (
    load_server_dkim_selector,
    load_server_transport,
    save_server_catch,
    save_server_direct,
    save_server_transport,
)

_TYPE = "email"
_DIRECT_DEFAULT_SELECTOR = "hop3"
# Public MX endpoints probed to tell whether outbound port 25 is open.
_EGRESS_PROBES = ("aspmx.l.google.com", "alt1.aspmx.l.google.com")


def _detect_server_ip() -> str:
    """The box's outbound source IP (for the SPF record). "" if undetectable.

    A UDP ``connect`` sends no packet — it just picks the source address the
    kernel would use for outbound traffic, which is the public IP on a VPS.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return str(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        return ""


def _egress_status() -> tuple[str, str]:
    """Whether outbound port 25 is open — three-state, never a fake 'ready'.

    Direct delivery is impossible if the host blocks outbound 25 (most clouds
    do). Skipped under tests (no network); otherwise a best-effort probe.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "unverified", "outbound port 25 not probed under tests"
    for host in _EGRESS_PROBES:
        try:
            with socket.create_connection((host, 25), timeout=5):
                return "present", f"outbound port 25 reaches {host}"
        except OSError:
            continue
    return "missing", (
        "outbound port 25 appears blocked — direct delivery cannot work; ask "
        "your host to unblock it, or use a relay backend"
    )


@register
@dataclass(frozen=True)
class ServerEmailSetCmd(Command):
    """Set the server-level shared email transport — EXPERIMENTAL.

    Usage: hop3 server email set (--provider <name> | --smtp-host <h>)
               --smtp-user <u> --smtp-password <pw> --from-domain <domain>
               [--smtp-port 587] [--dkim-selector <sel>]
           hop3 server email set --list-providers

    Stores the operator's SMTP submission credentials once, at the server
    level. Per-app email addons created without their own --smtp-* then inherit
    this transport (see `hop3 addon email create`), sending from any address on
    <domain>. Admin-only.

    `--provider <name>` fills --smtp-host/--smtp-port from a known profile
    (`--list-providers` to see them); you still supply --smtp-user/--smtp-password.
    `--dkim-selector` (or a provider with a fixed selector, e.g. resend) enables
    DKIM auto-verify in the deliverability pre-flight.

    Keep the password out of your shell history (ADR 036): `--smtp-password
    @<path>` reads it from a file and `--smtp-password -` reads it from stdin.

    Examples:
        hop3 server email set --provider brevo --smtp-user <u> \\
            --smtp-password @./smtp.secret --from-domain example.com
        hop3 server email set --smtp-host smtp.example.com --smtp-user u \\
            --smtp-password @./pw --from-domain example.com --dkim-selector s1
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("server", "email", "set")
    pass_username: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "provider": {"type": str},
        "smtp_host": {"type": str},
        # str (not int) so a non-numeric value yields a clean message below.
        "smtp_port": {"type": str, "default": "587"},
        "smtp_user": {"type": str},
        "smtp_password": {"type": str},
        "from_domain": {"type": str},
        "dkim_selector": {"type": str},
        "list_providers": {"flag": True},
    }

    def call(self, authenticated_username: str = "", *args: str) -> list[dict]:
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        parsed = parse_cli_args(args, self._arg_spec)
        if parsed.get("list_providers"):
            return _list_providers_items()

        resolved = self._resolve_endpoint(parsed, args)
        if isinstance(resolved, list):  # error items
            return resolved
        host, port_raw, profile = resolved

        built = self._build_transport(host, port_raw, parsed)
        if isinstance(built, list):  # error items
            return built
        transport, port, domain = built

        # An explicit --dkim-selector wins; otherwise a provider's fixed selector.
        selector = parsed.get("dkim_selector", "") or (
            profile.dkim_selector if profile else ""
        )

        # Configure the loopback relay FIRST — a failure must leave no
        # saved-but-unconfigured backend (fail-loud, never a fake success).
        try:
            configure_relay_backend(transport)
        except OnRampError as exc:
            return [error(str(exc))]

        with command_context("setting server email transport", service_type=_TYPE):
            save_server_transport(transport, dkim_selector=selector or None)

        return self._set_ok(host, port, domain, profile, selector)

    def _resolve_endpoint(
        self, parsed: dict, args: tuple[str, ...]
    ) -> list[dict] | tuple[str, str, ProviderProfile | None]:
        """Resolve the SMTP endpoint: ``--provider`` fills host/port from a
        profile, else ``--smtp-host``/``--smtp-port`` are used directly. Returns
        ``(host, port_raw, profile)`` or a loud error-item list."""
        raw_host = parsed.get("smtp_host", "")
        port_raw = parsed.get("smtp_port", "587")
        provider_name = parsed.get("provider", "")
        if not provider_name:
            return raw_host, port_raw, None

        profile = get_provider(provider_name)
        if profile is None:
            return [
                error(
                    f"unknown provider {provider_name!r}. Known: "
                    f"{provider_names()}. Or pass --smtp-host directly."
                )
            ]
        explicit_port = "--smtp-port" in args or any(
            str(a).startswith("--smtp-port=") for a in args
        )
        if raw_host or explicit_port:
            return [
                error(
                    "--provider already sets the SMTP host/port; don't also "
                    "pass --smtp-host / --smtp-port."
                )
            ]
        return profile.smtp_host, str(profile.smtp_port), profile

    def _build_transport(
        self, host: str, port_raw: str, parsed: dict
    ) -> list[dict] | tuple[EmailTransport, int, str]:
        """Validate the creds/domain and build the transport. Returns
        ``(transport, port, domain)`` or a loud error-item list."""
        user = parsed.get("smtp_user", "")
        password = parsed.get("smtp_password", "")
        domain = parsed.get("from_domain", "")

        missing = [
            flag
            for flag, val in (
                ("--smtp-host (or --provider)", host),
                ("--smtp-user", user),
                ("--smtp-password", password),
                ("--from-domain", domain),
            )
            if not val
        ]
        if missing:
            return [
                text(
                    "Usage: hop3 server email set (--provider <name> | "
                    "--smtp-host <h>) --smtp-user <u> --smtp-password <pw> "
                    "--from-domain <domain>"
                ),
                error(f"missing: {', '.join(missing)}"),
            ]

        if "@" in domain or "." not in domain:
            return [
                error(
                    f"--from-domain must be a bare domain (e.g. example.com), "
                    f"got {domain!r}"
                )
            ]

        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return [error(f"--smtp-port must be a whole number, got {port_raw!r}")]

        # Reuse EmailTransport's submission-port/TLS + control-char validation;
        # the server transport's default sender is noreply@<domain> (apps pick
        # their own From on the domain).
        try:
            transport = EmailTransport(
                smtp_host=host,
                smtp_port=port,
                smtp_user=user,
                smtp_password=password,
                mail_from=f"noreply@{domain}",
            )
        except ValueError as exc:
            return [error(str(exc))]
        return transport, port, domain

    def _set_ok(
        self,
        host: str,
        port: int,
        domain: str,
        profile: ProviderProfile | None,
        selector: str,
    ) -> list[dict]:
        lines = [
            warning(_EXPERIMENTAL_MSG),
            text(
                f"Server email transport set "
                f"(relay via {host}:{port}, sending domain {domain})."
            ),
            text(
                "\nApps inherit it — create one without --smtp-*:\n"
                f"  hop3 addon email create <name> --from noreply@{domain}"
            ),
        ]
        if profile and profile.spf_include:
            lines.append(
                text(
                    f"Publish SPF for {domain}: "
                    f"v=spf1 include:{profile.spf_include} ~all"
                )
            )
        if profile and profile.note:
            lines.append(text(f"Note ({profile.name}): {profile.note}"))
        lines.extend(_deliverability_items(domain, selector or None))
        lines.append(summary("set server email transport."))
        return lines


_BACKEND_KINDS = ("relay", "catch", "direct")

_BACKEND_USAGE = (
    "Usage: hop3 server email backend <relay|catch|direct> [options]\n"
    "  relay: (--provider <name> | --smtp-host <h>) --smtp-user <u> "
    "--smtp-password <pw> --from-domain <domain>"
)


@register
@dataclass(frozen=True)
class ServerEmailBackendCmd(Command):
    """Select the server-level email backend — EXPERIMENTAL.

    Usage: hop3 server email backend <relay|catch|direct> [backend options]

    Picks the backend every app inherits (ADR 054). `relay` submits to a
    provider or corporate smarthost — the shipped backend, also spelled
    `server email set`; pass its options after `relay`. `catch` (a dev sink)
    and `direct` (a self-hosted MTA) are not available yet and fail loud rather
    than pretend. Admin-only.

    Examples:
        hop3 server email backend relay --provider brevo --smtp-user <u> \\
            --smtp-password @./smtp.secret --from-domain example.com
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("server", "email", "backend")
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", *args: str) -> list[dict]:
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not args:
            return [text(_BACKEND_USAGE), error("missing: <relay|catch|direct>")]

        kind, *rest = args
        if kind == "relay":
            # `relay` delegates to `server email set`, which owns endpoint /
            # credential resolution, the loopback-relay config, and storage.
            return ServerEmailSetCmd(user_repo=self.user_repo).call(
                authenticated_username, *rest
            )
        if kind == "catch":
            return self._configure_catch(tuple(rest))
        if kind == "direct":
            return self._configure_direct(tuple(rest))
        return [
            text(_BACKEND_USAGE),
            error(f"unknown backend {kind!r}. Valid: {', '.join(_BACKEND_KINDS)}."),
        ]

    def _configure_catch(self, args: tuple[str, ...]) -> list[dict]:
        """Select the dev-catch backend: capture mail locally, never send it."""
        parsed = parse_cli_args(args, {"from_domain": {"type": str, "default": ""}})
        from_domain = parsed.get("from_domain", "") or "dev.local"
        if "@" in from_domain or "." not in from_domain:
            return [
                error(
                    "--from-domain must be a bare domain (e.g. example.com), "
                    f"got {from_domain!r}"
                )
            ]

        # Configure the loopback relay to point at the local sink FIRST, so a
        # failure leaves no saved-but-unconfigured backend (fail-loud).
        try:
            configure_catch_backend()
        except OnRampError as exc:
            return [error(str(exc))]

        with command_context("setting server email backend", service_type=_TYPE):
            save_server_catch(from_domain)

        return [
            warning(_EXPERIMENTAL_MSG),
            text(
                "Server email backend set to 'catch' — a dev sink; mail is "
                f"captured, not sent (domain {from_domain})."
            ),
            text(
                "\nApps inherit it — create one without --smtp-*:\n"
                f"  hop3 addon email create <name> --from noreply@{from_domain}"
            ),
            summary("set server email backend to catch."),
        ]

    def _configure_direct(self, args: tuple[str, ...]) -> list[dict]:
        """Select the direct backend: a Hop3-run MTA delivering to MX itself."""
        parsed = parse_cli_args(
            args,
            {
                "from_domain": {"type": str, "default": ""},
                "dkim_selector": {"type": str, "default": ""},
                "server_ip": {"type": str, "default": ""},
            },
        )
        from_domain = parsed.get("from_domain", "")
        if not from_domain or "@" in from_domain or "." not in from_domain:
            return [
                error(
                    "--from-domain <bare domain> (e.g. example.com) is required "
                    "for the direct backend"
                )
            ]
        selector = parsed.get("dkim_selector", "") or _DIRECT_DEFAULT_SELECTOR
        server_ip = parsed.get("server_ip", "") or _detect_server_ip()
        if not server_ip:
            return [
                error(
                    "could not determine the server's public IP for the SPF "
                    "record — pass --server-ip <ip>"
                )
            ]

        # Configure the MTA + DKIM first, so a failure leaves no saved-but-
        # unconfigured backend (fail-loud).
        try:
            result = configure_direct_backend(from_domain, server_ip, selector)
        except OnRampError as exc:
            return [error(str(exc))]

        with command_context("setting server email backend", service_type=_TYPE):
            save_server_direct(from_domain, selector)

        return self._direct_ok(from_domain, selector, server_ip, result)

    def _direct_ok(
        self,
        from_domain: str,
        selector: str,
        server_ip: str,
        result: dict[str, object] | None,
    ) -> list[dict]:
        lines: list[dict] = [
            warning(_EXPERIMENTAL_MSG),
            text(
                "Server email backend set to 'direct' — Hop3 delivers to "
                f"recipients' MX (sending IP {server_ip}, domain {from_domain})."
            ),
        ]
        raw = (result or {}).get("records")
        if isinstance(raw, dict):
            records = cast("dict[str, Any]", raw)
            lines.append(text("\nPublish these DNS records on your sending domain:"))
            for key in ("spf", "dkim", "dmarc"):
                rec = records.get(key)
                if isinstance(rec, dict):
                    lines.append(
                        text(f"  {rec['type']}  {rec['name']}\n    {rec['value']}")
                    )
            if records.get("ptr"):
                lines.append(text(f"  PTR — {records['ptr']}"))

        lines.extend(_deliverability_items(from_domain, selector))

        status, detail = _egress_status()
        lines.append(
            warning(detail) if status == "missing" else text(f"Egress: {detail}")
        )

        lines.append(
            text(
                "\nApps inherit it — create one without --smtp-*:\n"
                f"  hop3 addon email create <name> --from noreply@{from_domain}"
            )
        )
        lines.append(summary("set server email backend to direct."))
        return lines


@register
@dataclass(frozen=True)
class ServerEmailStatusCmd(Command):
    """Show the server-level shared email transport — EXPERIMENTAL.

    Usage: hop3 server email status

    Shows the configured relay host/port and verified sending domain, with an
    SPF/DMARC pre-flight on that domain. Never shows the password. Admin-only.
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("server", "email", "status")
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", *_args: str) -> list[dict]:
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        transport = load_server_transport()
        if transport is None:
            return [
                warning(_EXPERIMENTAL_MSG),
                warning("No server email transport is configured."),
                text(
                    "Set it: hop3 server email set --smtp-host <h> --smtp-user "
                    "<u> --smtp-password <pw> --from-domain <domain>"
                ),
            ]

        selector = load_server_dkim_selector()
        domain = transport.mail_from.rsplit("@", maxsplit=1)[-1]
        rows = [
            ["host", transport.smtp_host],
            ["port", str(transport.smtp_port)],
            ["sending domain", domain],
        ]
        if selector:
            rows.append(["dkim selector", selector])
        return [
            warning(_EXPERIMENTAL_MSG),
            table(headers=["Field", "Value"], rows=rows),
            *_deliverability_items(domain, selector),
        ]


def _list_providers_items() -> list[dict]:
    """Render the known provider profiles for `server email set --list-providers`."""
    rows = [
        [
            p.name,
            f"{p.smtp_host}:{p.smtp_port}",
            f"fixed: {p.dkim_selector}" if p.dkim_selector else "per-account",
            "EU" if p.eu_residency else "",
        ]
        for p in list_providers()
    ]
    return [
        warning(_EXPERIMENTAL_MSG),
        text("Known providers — `--provider <name>` fills --smtp-host/--smtp-port:"),
        table(headers=["provider", "smtp", "dkim", "residency"], rows=rows),
        text(
            "\nExample: hop3 server email set --provider brevo --smtp-user <u> "
            "--smtp-password <pw> --from-domain example.com"
        ),
    ]


# Contributed to the RPC dispatch table via EmailPlugin.cli_commands().
SERVER_COMMANDS: list[type[Command]] = [
    ServerEmailSetCmd,
    ServerEmailBackendCmd,
    ServerEmailStatusCmd,
]
