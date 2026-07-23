# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`env` is the canonical env-var group; `config` is a back-compat alias.

Regression for ADR 036's amendment: every `env <sub>` must also resolve via
`config <sub>` (server-side alias), and both must reach the same command.
"""

from __future__ import annotations

import pytest

from hop3.lib.scanner import scan_package
from hop3.server.controllers.rpc import find_command


@pytest.fixture(scope="module", autouse=True)
def _register():
    scan_package("hop3.commands")


# `migrate` moved to canonical `app migrate` (with `env`/`config migrate` aliases);
# its cross-alias resolution is covered by test_command_aliases.py.
@pytest.mark.parametrize("sub", ["show", "get", "set", "unset", "live"])
def test_config_alias_resolves_to_env_command(sub):
    env_cls, _ = find_command(["env", sub])
    config_cls, _ = find_command(["config", sub])
    assert env_cls is not None
    assert config_cls is env_cls
    assert env_cls.name == ("env", sub)


def test_bare_config_resolves_to_env_namespace():
    env_cls, _ = find_command(["env"])
    config_cls, _ = find_command(["config"])
    assert env_cls is config_cls is not None
    assert env_cls.name == ("env",)
