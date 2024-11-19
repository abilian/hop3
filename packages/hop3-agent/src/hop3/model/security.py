# Copyright (c) 2023-2024, Abilian SAS

# type: ignore

from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from flask_security import AsaList, RoleMixin, UserMixin
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

if TYPE_CHECKING:
    from datetime import datetime

AuditBase = BigIntAuditBase


class Role(AuditBase, RoleMixin):
    __tablename__ = "sec_role"

    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str]

    # A comma separated list of strings
    permissions = Column(MutableList.as_mutable(AsaList()), nullable=True)


class User(AuditBase, UserMixin):
    __tablename__ = "sec_user"

    email: Mapped[str] = mapped_column(unique=True)
    username: Mapped[str] = mapped_column(unique=True, nullable=True)
    password: Mapped[str]

    last_login_at: Mapped[datetime] = mapped_column(nullable=True)
    current_login_at: Mapped[datetime] = mapped_column(nullable=True)

    last_login_ip: Mapped[str] = mapped_column(default="")
    current_login_ip: Mapped[str] = mapped_column(default="")

    login_count: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool]

    fs_uniquifier: Mapped[str] = mapped_column(String(64), unique=True)
    confirmed_at: Mapped[datetime] = mapped_column(nullable=True)

    roles = relationship(
        Role, secondary="sec_users_roles", backref=backref("sec_user", lazy="dynamic")
    )

    @property
    def is_admin(self) -> bool:
        return False
        # return "admin" in [role.name for role in self.roles]


class RolesUsers(AuditBase):
    __tablename__ = "sec_users_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    role_id: Mapped[int] = mapped_column(ForeignKey(Role.id))
