# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Named email-provider profiles (EXPERIMENTAL).

Declarative data so an operator can say ``server email set --provider brevo``
instead of typing the raw ``--smtp-host``/``--smtp-port``. A profile carries the
provider's SMTP submission endpoint, its SPF ``include:`` token (for a
publish-this hint), and — **only where the provider uses a fixed, provider-wide
selector** — its DKIM selector, which unlocks DKIM auto-verify without the
operator supplying one.

DKIM reality (from provider docs): only **Resend** exposes a fixed selector
(``resend``). Postmark, Brevo, Mailgun, Scaleway and SES all mint a
per-account/per-identity selector shown in their dashboard, so for those the
operator passes ``--dkim-selector`` (or DKIM stays a guidance row) — Hop3 never
guesses a selector and reports a fake "missing".

Amazon SES is deliberately **not** listed here: its endpoint is region-templated
(``email-smtp.<region>.amazonaws.com``) and its DKIM is per-identity, so it
belongs with the "needs real logic" provider slice (release-plan-0.7 M3.1),
alongside the IAM→SMTP-password derivation. A data-only SES profile is feasible
(the console hands out ready SMTP creds) and can be added once region handling
lands.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """One transactional-email provider's submission + deliverability shape."""

    name: str
    smtp_host: str
    smtp_port: int = 587  # STARTTLS submission — the documented default for all
    spf_include: str = ""  # "" when it isn't a simple root-domain include (Resend)
    dkim_selector: str = ""  # a fixed provider-wide selector, or "" if per-account
    eu_residency: bool = False
    note: str = ""


# All hosts/ports/includes below are from each provider's own documentation
# (2026-07). Only Resend carries a fixed DKIM selector.
_PROFILES: list[ProviderProfile] = [
    ProviderProfile(
        "resend",
        "smtp.resend.com",
        dkim_selector="resend",
        note="publishes SPF + a feedback MX on a `send.` subdomain — follow "
        "Resend's DNS setup rather than a plain root-domain SPF include.",
    ),
    ProviderProfile("postmark", "smtp.postmarkapp.com", spf_include="spf.mtasv.net"),
    ProviderProfile(
        "brevo", "smtp-relay.brevo.com", spf_include="spf.brevo.com", eu_residency=True
    ),
    ProviderProfile("mailgun", "smtp.mailgun.org", spf_include="mailgun.org"),
    ProviderProfile(
        "mailgun-eu",
        "smtp.eu.mailgun.org",
        spf_include="mailgun.org",
        eu_residency=True,
    ),
    ProviderProfile(
        "scaleway",
        "smtp.tem.scaleway.com",
        spf_include="_spf.tem.scaleway.com",
        eu_residency=True,
        note="French-sovereign (fr-par). Verify the SPF include against your "
        "Scaleway console — the published value has changed across doc versions.",
    ),
]

PROVIDERS: dict[str, ProviderProfile] = {p.name: p for p in _PROFILES}


def get_provider(name: str) -> ProviderProfile | None:
    """The profile for ``name`` (case-insensitive), or None if unknown."""
    return PROVIDERS.get(name.strip().lower())


def list_providers() -> list[ProviderProfile]:
    """All known provider profiles, in registry order."""
    return list(_PROFILES)


def provider_names() -> str:
    """Comma-joined provider names, for error/usage messages."""
    return ", ".join(PROVIDERS)
