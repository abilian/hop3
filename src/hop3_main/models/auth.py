# Copyright (c) 2019-2024, Abilian SAS - All rights reserved

from __future__ import annotations

from datetime import datetime

from flask_security import AsaList, RoleMixin, UserMixin
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from ._base import AuditBase, Repository, RepositoryService


class Role(AuditBase, RoleMixin):
    __tablename__ = "sec_role"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255))

    # A comma separated list of strings
    permissions: Mapped[MutableList] = mapped_column(
        MutableList.as_mutable(AsaList()),
        nullable=True,
    )


class User(AuditBase, UserMixin):
    __tablename__ = "sec_user"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    password: Mapped[str] = mapped_column(String(255))

    last_login_at: Mapped[datetime] = mapped_column(nullable=True)
    current_login_at: Mapped[datetime] = mapped_column(nullable=True)

    last_login_ip: Mapped[str] = mapped_column(String(100), nullable=True)
    current_login_ip: Mapped[str] = mapped_column(String(100), nullable=True)

    login_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=False)

    fs_uniquifier: Mapped[str] = mapped_column(String(64), unique=True)
    confirmed_at: Mapped[datetime] = mapped_column(nullable=True)

    roles = relationship(
        Role, secondary="sec_users_roles", backref=backref("sec_user", lazy="dynamic")
    )

    @property
    def is_admin(self):
        return "admin" in {role.name for role in self.roles}


class RolesUsers(AuditBase):
    __tablename__ = "sec_users_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    role_id: Mapped[int] = mapped_column(ForeignKey(Role.id))


class UserRepository(Repository[User]):
    model_type = User


class UserService(RepositoryService[User]):
    repository_type = UserRepository


class RoleRepository(Repository[Role]):
    model_type = Role


class RoleService(RepositoryService[Role]):
    repository_type = RoleRepository
