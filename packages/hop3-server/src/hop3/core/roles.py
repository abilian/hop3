# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The standard roles (ADR 061).

Four fixed roles belong to the platform; no command creates, renames or
deletes one. They are totally ordered, and each includes everything the roles
below it grant. Declaration order is that order, lowest first.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """A standard role. A command or a gate names the *minimum* it requires."""

    MEMBER = "member"
    VIEWER = "viewer"
    DEPLOYER = "deployer"
    ADMIN = "admin"

    def includes(self, required: Role) -> bool:
        """True when this role grants at least what ``required`` grants."""
        order = list(Role)
        return order.index(self) >= order.index(required)

    @classmethod
    def parse(cls, value: str) -> Role:
        """
        The role named ``value``, or a ValueError that lists the valid names.

        For input from a command line; the message is shown to the user as is.
        """
        try:
            return cls(value)
        except ValueError:
            valid = ", ".join(role.value for role in cls)
            msg = f"Unknown role {value!r}. The roles are: {valid}."
            raise ValueError(msg) from None
