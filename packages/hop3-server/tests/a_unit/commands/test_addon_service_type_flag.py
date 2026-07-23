# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Addon commands must honour --service-type (the flag demos/users actually use).

Regression: attach/detach/destroy/show only read --type (default "postgres"),
so `hop3 addon attach myredis --app app --service-type redis` silently treated
the redis addon as postgres — breaking every non-postgres addon demo.
"""

from __future__ import annotations

import pytest

from hop3.commands.services import (
    AddonAttachCmd,
    AddonDestroyCmd,
    AddonDetachCmd,
    AddonShowCmd,
)
from hop3.lib.args import parse_cli_args

_SPECS = [AddonAttachCmd, AddonDetachCmd, AddonDestroyCmd, AddonShowCmd]


def _resolve(spec: dict, args: tuple) -> str:
    """Mirror the command's service_type resolution."""
    parsed = parse_cli_args(args, spec)
    return parsed.get("service_type") or parsed.get("type", "postgres")


@pytest.mark.parametrize("cmd", _SPECS)
def test_service_type_flag_is_honored(cmd):
    assert _resolve(cmd._arg_spec, ("mydb", "--service-type", "redis")) == "redis"


@pytest.mark.parametrize("cmd", _SPECS)
def test_type_flag_still_works(cmd):
    assert _resolve(cmd._arg_spec, ("mydb", "--type", "mysql")) == "mysql"


@pytest.mark.parametrize("cmd", _SPECS)
def test_defaults_to_postgres_when_unspecified(cmd):
    assert _resolve(cmd._arg_spec, ("mydb",)) == "postgres"


def test_attach_parses_name_and_app_alongside_service_type():
    parsed = parse_cli_args(
        ("demo14-redis", "--app", "demo14", "--service-type", "redis"),
        AddonAttachCmd._arg_spec,
    )
    assert parsed["addon_name"] == "demo14-redis"
    assert parsed["app"] == "demo14"
    assert parsed.get("service_type") == "redis"
