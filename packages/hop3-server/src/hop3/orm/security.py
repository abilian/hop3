# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Security models for user authentication and authorization."""

from __future__ import annotations

from datetime import datetime

import bcrypt as bcrypt_lib
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

AuditBase = BigIntAuditBase


# Association table for many-to-many relationship between users and roles
users_roles = Table(
    "sec_users_roles",
    AuditBase.metadata,
    Column("user_id", ForeignKey("sec_user.id"), primary_key=True),
    Column("role_id", ForeignKey("sec_role.id"), primary_key=True),
)


class Role(AuditBase):
    """Security role for user access control."""

    __tablename__ = "sec_role"

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    # Relationships
    users: Mapped[list[User]] = relationship(
        "User", secondary=users_roles, back_populates="roles"
    )

    def __repr__(self) -> str:
        return f"<Role(name='{self.name}')>"


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

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role", secondary=users_roles, back_populates="users"
    )

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', email='{self.email}')>"

    def set_password(self, password: str) -> None:
        """Hash and set the user's password.

        Args:
            password: The plain text password to hash
        """
        password_bytes = password.encode("utf-8")
        salt = bcrypt_lib.gensalt()
        hashed = bcrypt_lib.hashpw(password_bytes, salt)
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify a password against the hash.

        Args:
            password: The plain text password to check

        Returns:
            True if the password matches, False otherwise
        """
        password_bytes = password.encode("utf-8")
        hash_bytes = self.password_hash.encode("utf-8")
        return bcrypt_lib.checkpw(password_bytes, hash_bytes)

    def has_role(self, role_name: str) -> bool:
        """Check if the user has a specific role.

        Args:
            role_name: The name of the role to check

        Returns:
            True if the user has the role, False otherwise
        """
        return any(role.name == role_name for role in self.roles)

    @property
    def is_admin(self) -> bool:
        """Check if the user is an administrator.

        Returns:
            True if the user has the 'admin' role, False otherwise
        """
        return self.has_role("admin")
