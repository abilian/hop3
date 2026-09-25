# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The role guard for Litestar routes (ADR 061 §4).

Every dashboard route names the lowest role that may open it; the guard reads
the caller's account and admits it only when active and in that role or above.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from litestar.exceptions import NotAuthorizedException, PermissionDeniedException

from hop3 import config
from hop3.server.security.authorization import lookup_account
from hop3.server.security.web_auth import current_identity

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler

    from hop3.core.roles import Role


@dataclass(frozen=True)
class RoleGuard:
    """
    Admit an active account whose role includes ``required`` (ADR 061 §4).

    The dashboard's counterpart of the RPC dispatcher's check, on the same
    account lookup: the role is read from the database on every request.
    ``required`` stays readable, so a test can map every route to its role.
    """

    required: Role

    def __call__(self, connection: ASGIConnection, _: BaseRouteHandler) -> None:
        # As in the RPC dispatcher: the bypass is refused outside development.
        if config.HOP3_UNSAFE:
            return

        identity = current_identity(connection)
        if not identity:
            raise NotAuthorizedException(detail="Authentication required")

        account = lookup_account(str(identity.get("username", "")))
        if account is None or not account.active:
            raise NotAuthorizedException(detail="Account unknown or disabled")

        if not account.role.includes(self.required):
            msg = (
                f"This page needs the {self.required} role; account "
                f"'{account.username}' is {account.role}. An admin can grant "
                f"it: hop3 user set-role {account.username} {self.required}"
            )
            raise PermissionDeniedException(detail=msg)
