# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deliverability pre-flight for the email addon — SPF/DKIM/DMARC DNS checks.

Hop3 relays through the operator's provider; whether mail reaches the inbox is
gated by DNS on the From-domain, not by Hop3. This module does a best-effort
check (via ``dig`` — commonly present, no new dependency) so the addon can
surface what's missing and never report "ready" over unpublished DNS.

A missing resolver yields ``UNKNOWN`` — distinct from ``MISSING`` — so the addon
never reports a fake "missing" (or a fake "ready"). SPF and DMARC are
provider-independent and auto-checked; DKIM is provider-specific (its selector
comes from the provider's dashboard) and surfaced as guidance, not auto-verified.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

# Bound per-query latency so `create`/`status` stay responsive even when a
# resolver is slow; the check is best-effort and never fatal.
_DIG_TIMEOUT_S = 5
_DIG_ARGS = ["+short", "+time=3", "+tries=1", "TXT"]

PRESENT = "present"
MISSING = "missing"
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DnsCheck:
    """The result of looking for one record type on a domain."""

    label: str  # "SPF" / "DMARC"
    status: str  # PRESENT / MISSING / UNKNOWN
    detail: str  # the found record, or a what-to-publish hint


def lookup_txt(name: str) -> list[str] | None:
    """TXT records for ``name``, or None when no resolver is available.

    Uses ``dig`` (no new dependency). A missing ``dig``, a non-zero exit, or a
    timeout returns None — "unknown", distinct from an empty list ("no records")
    — so the caller never reports a fake "missing".
    """
    try:
        proc = subprocess.run(
            ["dig", *_DIG_ARGS, name],
            capture_output=True,
            text=True,
            timeout=_DIG_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return [_unquote(line) for line in proc.stdout.splitlines() if line.strip()]


def _unquote(line: str) -> str:
    """Join ``dig``'s quoted TXT chunks (`"a" "b"` → `ab`) into the record."""
    return line.replace('" "', "").strip().strip('"')


def check_spf(domain: str) -> DnsCheck:
    return _classify(
        "SPF",
        lookup_txt(domain),
        marker="v=spf1",
        hint=(
            f"add a TXT record on {domain} authorizing your provider, e.g. "
            "`v=spf1 include:<your-provider> ~all` (exact include from the provider)"
        ),
    )


def check_dmarc(domain: str) -> DnsCheck:
    return _classify(
        "DMARC",
        lookup_txt(f"_dmarc.{domain}"),
        marker="v=DMARC1",
        hint=(
            f"add a TXT record at _dmarc.{domain}: "
            f"`v=DMARC1; p=none; rua=mailto:postmaster@{domain}`"
        ),
    )


def _classify(
    label: str, records: list[str] | None, *, marker: str, hint: str
) -> DnsCheck:
    if records is None:
        return DnsCheck(
            label, UNKNOWN, "DNS check unavailable (install `dig` / dnsutils)"
        )
    for record in records:
        if marker.lower() in record.lower():
            return DnsCheck(label, PRESENT, record)
    return DnsCheck(label, MISSING, hint)
