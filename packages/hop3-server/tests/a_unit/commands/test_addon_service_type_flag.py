# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Addon commands must honour --service-type (the flag demos/users actually use).

Regression: attach/detach/destroy/show only read --type (default "postgres"),
so `hop3 addon attach myredis --app app --service-type redis` silently treated
the redis addon as postgres — breaking every non-postgres addon demo. Without
either flag, the addon's own name decides its type (`addon status` crashed on
every call reading a `type` key its spec never declared).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hop3.commands import services
from hop3.commands.services import (
    AddonAttachCmd,
    AddonDestroyCmd,
    AddonDetachCmd,
    AddonShowCmd,
    AddonStatusCmd,
    _resolve_one_type,
)
from hop3.lib.args import parse_cli_args

_SPECS = [AddonAttachCmd, AddonDetachCmd, AddonDestroyCmd, AddonShowCmd, AddonStatusCmd]


def _resolve(spec: dict, args: tuple) -> str:
    """The type the command resolves for ``args``."""
    return _resolve_one_type(args[0], parse_cli_args(args, spec))


@pytest.mark.parametrize("cmd", _SPECS)
def test_service_type_flag_is_honored(cmd):
    assert _resolve(cmd._arg_spec, ("mydb", "--service-type", "redis")) == "redis"


@pytest.mark.parametrize("cmd", _SPECS)
def test_type_flag_still_works(cmd):
    assert _resolve(cmd._arg_spec, ("mydb", "--type", "mysql")) == "mysql"


@pytest.mark.parametrize("cmd", _SPECS)
def test_unspecified_type_is_the_named_addons(cmd):
    """No --type: the addon's own type, never an assumed postgres."""
    with patch.object(
        services, "list_addon_instances", return_value=[("redis", "mydb")]
    ):
        assert _resolve(cmd._arg_spec, ("mydb",)) == "redis"


@pytest.mark.parametrize("cmd", _SPECS)
def test_unknown_name_without_type_is_refused(cmd):
    with (
        patch.object(services, "list_addon_instances", return_value=[]),
        pytest.raises(ValueError, match="No addon named 'mydb'"),
    ):
        _resolve(cmd._arg_spec, ("mydb",))


@pytest.mark.parametrize("cmd", _SPECS)
def test_shared_name_without_type_is_refused(cmd):
    instances = [("postgres", "mydb"), ("redis", "mydb")]
    with (
        patch.object(services, "list_addon_instances", return_value=instances),
        pytest.raises(ValueError, match="ambiguous"),
    ):
        _resolve(cmd._arg_spec, ("mydb",))


def test_attach_parses_name_and_app_alongside_service_type():
    parsed = parse_cli_args(
        ("demo14-redis", "--app", "demo14", "--service-type", "redis"),
        AddonAttachCmd._arg_spec,
    )
    assert parsed["addon_name"] == "demo14-redis"
    assert parsed["app"] == "demo14"
    assert parsed.get("service_type") == "redis"
