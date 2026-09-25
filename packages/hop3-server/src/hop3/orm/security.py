# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Security models for user authentication and authorization."""

from __future__ import annotations

from datetime import datetime

import bcrypt as bcrypt_lib
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from hop3.core.roles import Role

AuditBase = BigIntAuditBase


# SECURITY: a real bcrypt hash of a value nothing can authenticate as, used to
# spend the same CPU on a nonexistent username as on a real one. Without it,
# "no such user" returns in microseconds while "wrong password" takes bcrypt's
# ~100ms, and the difference enumerates the user table regardless of how
# carefully the two responses are worded (CWE-204). Generated once at import
# rather than per call: `checkpw` is what has to cost, not `hashpw`.
_DUMMY_PASSWORD_HASH = bcrypt_lib.hashpw(
    b"hop3-timing-equalisation-placeholder", bcrypt_lib.gensalt()
)


def burn_password_check(password: str) -> None:
    """
    Verify `password` against a throwaway hash and discard the result.

    Call this on the "user not found" branch of any login path so its
    response time matches the "user found, wrong password" branch. Keep it
    behind a rate limiter — it is deliberately expensive, which is a DoS
    lever if an unauthenticated caller can drive it without limit.
    """
    bcrypt_lib.checkpw(password.encode("utf-8"), _DUMMY_PASSWORD_HASH)


class User(AuditBase):
    """User entity for authentication and authorization."""

    __tablename__ = "sec_user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Authentication tracking
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    current_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(45), default="")
    current_login_ip: Mapped[str] = mapped_column(String(45), default="")
    login_count: Mapped[int] = mapped_column(default=0)

    # Status
    active: Mapped[bool] = mapped_column(default=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # The account's one server role (ADR 061 §2). Stored as its value, so the
    # column reads "admin" rather than an enum member name.
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            native_enum=False,
            length=16,
            values_callable=lambda roles: [role.value for role in roles],
        ),
        default=Role.MEMBER,
        server_default=Role.MEMBER.value,
    )

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', email='{self.email}')>"

    def set_password(self, password: str) -> None:
        """
        Hash and set the user's password.

        Args:
            password: The plain text password to hash
        """
        password_bytes = password.encode("utf-8")
        salt = bcrypt_lib.gensalt()
        hashed = bcrypt_lib.hashpw(password_bytes, salt)
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, password: str) -> bool:
        """
        Verify a password against the hash.

        Args:
            password: The plain text password to check

        Returns:
            True if the password matches, False otherwise
        """
        password_bytes = password.encode("utf-8")
        hash_bytes = self.password_hash.encode("utf-8")
        return bcrypt_lib.checkpw(password_bytes, hash_bytes)

    @property
    def is_admin(self) -> bool:
        """True when the account holds the ``admin`` role."""
        return self.role is Role.ADMIN
