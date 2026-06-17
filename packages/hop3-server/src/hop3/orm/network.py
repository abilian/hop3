# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Operator-defined named networks — CIDR sets referenced by WAF gates.

A WAF access gate (ADR 048 §2, ``[[waf.gate]] require = "office"``) names a
network rather than hard-coding CIDRs in the app's ``hop3.toml``: the operator
owns the address ranges (office / VPN), they can change without redeploying the
app, and the app config stays portable across servers. Networks are host-wide
runtime state managed via ``hop3 network`` (and, later, the admin UI).
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Network(BigIntAuditBase):
    """A named set of CIDRs (IPv4 or IPv6), referenced by name from WAF gates."""

    __tablename__ = "network"

    # Reference key used in [[waf.gate]] require = "<name>". Unique host-wide.
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Canonical-form CIDRs, e.g. ["203.0.113.0/24", "10.0.0.0/8"].
    cidrs: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_network_name"),)
