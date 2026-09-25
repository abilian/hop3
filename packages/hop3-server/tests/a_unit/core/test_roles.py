# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The standard roles are totally ordered, and each includes those below it."""

from __future__ import annotations

import pytest

from hop3.core.roles import Role


def test_the_order_is_member_viewer_deployer_admin():
    assert list(Role) == [Role.MEMBER, Role.VIEWER, Role.DEPLOYER, Role.ADMIN]


@pytest.mark.parametrize("role", list(Role))
def test_every_role_includes_itself_and_member(role: Role):
    assert role.includes(role)
    assert role.includes(Role.MEMBER)


def test_a_role_does_not_include_the_ones_above_it():
    assert Role.DEPLOYER.includes(Role.VIEWER)
    assert not Role.VIEWER.includes(Role.DEPLOYER)
    assert not Role.DEPLOYER.includes(Role.ADMIN)
    assert Role.ADMIN.includes(Role.DEPLOYER)


def test_parse_names_the_valid_roles_on_a_typo():
    assert Role.parse("viewer") is Role.VIEWER
    with pytest.raises(ValueError, match="member, viewer, deployer, admin"):
        Role.parse("editor")
