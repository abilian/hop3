# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI command: list fixed host-port claims (the [[ports]] registry)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register
from hop3.orm import PortClaimRepository

from ._base import Command
from ._response import table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class PortsCmd(Command):
    """List the fixed host ports apps have claimed.

    Non-HTTP apps declare the ports they bind directly via [[ports]] in
    hop3.toml. Each becomes a host-wide claim: exactly one app can own a
    given port. This shows every claim, who holds it, the source it is
    opened to, and whether the firewall rule is actually open.

    The "Firewall" column reads 'open' once hop3-rootd has applied the rule,
    or 'claimed' when the port is reserved (conflict-checked) but not yet
    open — Docker apps (the container doesn't publish the port) or a
    deploy made while hop3-rootd was unavailable.

    Examples:
        hop3 ports                     # alias for 'port list'
        hop3 port list                 # canonical form
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("port", "list")

    def call(self, *args):
        if args:
            got = " ".join(args)
            msg = f"'hop3 port list' takes no arguments (got: {got})."
            raise ValueError(msg)

        repo = PortClaimRepository(session=self.db_session)
        claims = sorted(repo.get_many(), key=lambda c: (c.number, c.protocol))
        if not claims:
            return [text("No fixed host ports are claimed.")]

        rows = [
            [
                claim.number,
                claim.protocol,
                claim.app_name,
                claim.source,
                "open" if claim.rule_id else "claimed",
            ]
            for claim in claims
        ]
        return [
            table(
                headers=["Port", "Proto", "App", "Source", "Firewall"],
                rows=rows,
            )
        ]
