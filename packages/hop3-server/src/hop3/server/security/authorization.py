# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The caller's account, as the control plane authorizes it (ADR 061).

The RPC dispatcher and the dashboard's guards decide on the same thing: the
account a token names, read from the database when the request arrives. A
token carries a name, never an authority, so a demotion or a disabled account
takes effect on the next request without revoking anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.orm import get_session_factory
from hop3.orm.repositories import UserRepository

if TYPE_CHECKING:
    from hop3.core.roles import Role


@dataclass(frozen=True, slots=True)
class Account:
    """What authorization needs to know about an account, read at one moment."""

    username: str
    role: Role
    active: bool


def lookup_account(username: str) -> Account | None:
    """The account ``username`` names, read now; None when there is none."""
    with get_session_factory()() as db_session:
        user = UserRepository(session=db_session).get_by_username(username)
        if user is None:
            return None
        return Account(username=user.username, role=user.role, active=user.active)
