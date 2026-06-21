# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for operator-defined named networks (ADR 050 §2).

A named network is a set of CIDRs the operator manages once and references by
name from a WAF gate (``[[waf.gate]] require = "office"``). Keeping the CIDRs
here — not in app configs — means the operator owns the ranges, they change
without redeploying apps, and app configs stay portable.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register
from hop3.orm import Network, NetworkRepository

from ._base import Command
from ._response import error, summary, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Network names appear unquoted in hop3.toml and on the CLI; keep them
# identifier-shaped. "auth" is reserved — it's the gate keyword for Hop3
# forward-auth, so a network of that name would be ambiguous.
_NETWORK_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
_RESERVED_NETWORK_NAMES = frozenset({"auth", "any"})


def _validate_cidrs(raw: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Validate + canonicalise CIDRs (IPv4 or IPv6). Returns (cidrs, errors)."""
    cidrs: list[str] = []
    errors: list[str] = []
    for c in raw:
        try:
            cidrs.append(str(ipaddress.ip_network(c, strict=False)))
        except (ValueError, TypeError) as e:
            errors.append(f"'{c}' is not a valid CIDR: {e}")
    return cidrs, errors


@register
@dataclass(frozen=True)
class NetworkListCmd(Command):
    """List operator-defined named networks.

    Examples:
        hop3 networks                  # alias for 'network list'
        hop3 network list              # canonical form
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("network", "list")

    def call(self, *args):
        if args:
            msg = f"'hop3 network list' takes no arguments (got: {' '.join(args)})."
            raise ValueError(msg)
        repo = NetworkRepository(session=self.db_session)
        networks = sorted(repo.get_many(), key=lambda n: n.name)
        if not networks:
            return [text("No named networks defined.")]
        rows = [[n.name, ", ".join(n.cidrs)] for n in networks]
        return [table(headers=["Name", "CIDRs"], rows=rows)]


@register
@dataclass(frozen=True)
class NetworkAddCmd(Command):
    """Define or replace a named network (a set of CIDRs).

    Re-adding an existing name replaces its CIDRs.

    Examples:
        hop3 network add office 203.0.113.0/24
        hop3 network add vpn 10.8.0.0/24 fd00::/8
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("network", "add")

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop3 network add <name> <cidr> [<cidr> ...]")]
        net_name, *cidr_args = args

        if net_name in _RESERVED_NETWORK_NAMES:
            return [
                error(
                    f"'{net_name}' is reserved and can't be a network name "
                    f"(reserved: {', '.join(sorted(_RESERVED_NETWORK_NAMES))})."
                )
            ]
        if not _NETWORK_NAME_RE.match(net_name):
            return [
                error(
                    f"Invalid network name '{net_name}'. Use a letter followed by "
                    "letters, digits, '-' or '_'."
                )
            ]

        cidrs, errors = _validate_cidrs(tuple(cidr_args))
        if errors:
            return [error("\n".join(errors))]

        repo = NetworkRepository(session=self.db_session)
        existing = repo.get_by_name(net_name)
        if existing is not None:
            existing.cidrs = cidrs
            verb = "Updated"
        else:
            self.db_session.add(Network(name=net_name, cidrs=cidrs))
            verb = "Defined"
        self.db_session.commit()

        return [
            text(f"{verb} network '{net_name}': {', '.join(cidrs)}"),
            summary(f"{verb.lower()} network {net_name}"),
        ]


@register
@dataclass(frozen=True)
class NetworkRmCmd(Command):
    """Remove a named network.

    A gate that still references it will fail to resolve at deploy time, so
    remove the reference from the app's hop3.toml too.

    Examples:
        hop3 network rm office
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("network", "rm")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if len(args) != 1:
            return [text("Usage: hop3 network rm <name>")]
        net_name = args[0]
        repo = NetworkRepository(session=self.db_session)
        net = repo.get_by_name(net_name)
        if net is None:
            return [error(f"No network named '{net_name}'.")]
        self.db_session.delete(net)
        self.db_session.commit()
        return [
            text(f"Removed network '{net_name}'."),
            summary(f"removed network {net_name}"),
        ]
