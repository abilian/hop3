# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The [admin] section: schema validation + Hop3Config accessor (ADR 056)."""

from __future__ import annotations

import pytest
import tomllib
from pydantic import ValidationError

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import AdminSection, Hop3TomlSchema


def _validate(admin_toml: str) -> Hop3TomlSchema:
    data = tomllib.loads('[metadata]\nid = "x"\n' + admin_toml)
    return Hop3TomlSchema.model_validate(data)


def test_email_operator_form_is_valid():
    m = _validate(
        '[admin]\nemail = "operator"\npassword = { generate = "password", length = 24 }\n'
    )
    assert m.admin is not None
    assert m.admin.email == "operator"
    assert m.admin.password.generate == "password"
    assert m.admin.username is None


def test_username_only_is_valid():
    m = _validate('[admin]\nusername = "admin"\npassword = { generate = "password" }\n')
    assert m.admin is not None
    assert m.admin.username == "admin"
    assert m.admin.email is None


def test_literal_email_is_valid():
    m = _validate(
        '[admin]\nemail = "ops@example.com"\npassword = { generate = "password" }\n'
    )
    assert m.admin is not None
    assert m.admin.email == "ops@example.com"


@pytest.mark.parametrize(
    "admin_toml",
    [
        # neither username nor email
        '[admin]\npassword = { generate = "password" }\n',
        # email is neither "operator" nor a literal address
        '[admin]\nemail = "notanemail"\npassword = { generate = "password" }\n',
        # a bare "@" is not a valid literal address
        '[admin]\nemail = "@"\npassword = { generate = "password" }\n',
        # whitespace-only username is blank
        '[admin]\nusername = " "\npassword = { generate = "password" }\n',
        # missing password
        '[admin]\nusername = "admin"\n',
        # unknown key
        '[admin]\nusername = "a"\npassword = { generate = "password" }\nnope = 1\n',
    ],
)
def test_invalid_admin_sections_are_rejected(admin_toml):
    with pytest.raises(ValidationError):
        _validate(admin_toml)


def test_hop3config_admin_getter():
    data = tomllib.loads(
        '[metadata]\nid = "x"\n[admin]\nemail = "operator"\n'
        'password = { generate = "password" }\ncreate = "make-admin"\n'
    )
    cfg = Hop3Config(_data=data)
    assert cfg.admin["email"] == "operator"
    assert cfg.admin["create"] == "make-admin"


def test_hop3config_admin_getter_absent():
    cfg = Hop3Config(_data=tomllib.loads('[metadata]\nid = "x"\n'))
    assert cfg.admin == {}


# [admin].login — which identifier the app's sign-in form takes


def test_admin_login_accepts_username_and_email():
    assert (
        AdminSection(
            username="admin", password={"generate": "password"}, login="username"
        ).login
        == "username"
    )
    assert (
        AdminSection(
            email="a@b.com", password={"generate": "password"}, login="email"
        ).login
        == "email"
    )


def test_admin_login_defaults_to_unset():
    """Unset keeps the old display (both listed) — no migration needed."""
    section = AdminSection(username="admin", password={"generate": "password"})
    assert section.login is None


def test_admin_login_rejects_an_undeclared_identifier():
    """
    Pointing `login` at an identifier the recipe never declares must fail loud.

    Otherwise the reveal names a sign-in field that has no value behind it.
    """
    with pytest.raises(ValidationError, match="no `email` is declared"):
        AdminSection(username="admin", password={"generate": "password"}, login="email")

    with pytest.raises(ValidationError, match="no `username` is declared"):
        AdminSection(
            email="a@b.com", password={"generate": "password"}, login="username"
        )


def test_admin_login_rejects_an_unknown_value():
    with pytest.raises(ValidationError):
        AdminSection(
            username="admin", password={"generate": "password"}, login="nickname"
        )


# [deploy].allow-http


def test_deploy_allow_http_defaults_to_false():
    """Default is the HTTPS redirect, so recipes need declare nothing."""
    config = Hop3Config.from_str("[build]\nbuilder = 'local'\n")
    assert config.allow_http is False


def test_deploy_allow_http_is_read_from_the_recipe():
    config = Hop3Config.from_str("[deploy]\nallow-http = true\n")
    assert config.allow_http is True


def test_deploy_allow_http_accepts_the_schema():
    """The kebab-case alias must validate (extra='forbid' otherwise rejects)."""
    Hop3TomlSchema.model_validate({"deploy": {"allow-http": True}})
