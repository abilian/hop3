# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The [access] section: who may reach an app (ADR 062)."""

from __future__ import annotations

import pytest

from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def access(**section) -> object:
    return validate_hop3_toml({"access": section}).access


def test_an_app_is_open_unless_it_says_otherwise():
    section = access()
    assert (section.require, section.role, section.public_paths) == (
        "none",
        "member",
        [],
    )


def test_a_gated_app_names_its_role_and_public_paths():
    section = access(require="auth", role="viewer", **{"public-paths": ["/hook"]})
    assert (section.require, section.role, section.public_paths) == (
        "auth",
        "viewer",
        ["/hook"],
    )


@pytest.mark.parametrize(
    ("section", "reason"),
    [
        ({"require": "yes"}, "'auth' or 'none'"),
        ({"role": "owner"}, "The roles are: member, viewer, deployer, admin"),
        ({"public-paths": ["("]}, r"\[access\] path pattern '\(' is not a valid regex"),
        ({"public-path": ["/hook"]}, "Unknown field 'access -> public-path'"),
    ],
)
def test_a_malformed_section_is_refused_at_load(section, reason):
    with pytest.raises(Hop3TomlValidationError, match=reason):
        validate_hop3_toml({"access": section})
