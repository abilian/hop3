# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for `[contexts.*]` in hop3.toml (ADR 042, 2nd revision).

A context is a non-secret deploy environment (server address, app, domains,
env). The schema *accepts* it (so committed files validate and git-push), the
deployer *ignores* it, and a committed-credential tripwire keeps it secret-free.
"""

from __future__ import annotations

import pytest

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError

VALID = """
[metadata]
id = "myapp"

[contexts.dev]
server = "ssh://root@dev.example.com"
app = "myapp-dev"
[contexts.dev.domains]
list = ["myapp.dev.example.com"]
[contexts.dev.env]
LOG_LEVEL = "debug"

[contexts.prod]
server = "ssh://root@prod.example.com"
app = "myapp"
[contexts.prod.domains]
list = ["myapp.com"]
[contexts.prod.env]
LOG_LEVEL = "warning"
"""


def test_valid_contexts_accepted():
    cfg = Hop3Config.from_str(VALID)
    # Deployer-facing config is unaffected by [contexts.*].
    assert cfg.app_id == "myapp"


def _reject(content: str, needle: str) -> None:
    with pytest.raises(Hop3TomlValidationError) as exc:
        Hop3Config.from_str(content)
    assert needle in str(exc.value)


def test_secret_in_context_env_rejected():
    _reject(
        '[metadata]\nid="a"\n[contexts.prod]\nserver="ssh://root@h"\n'
        '[contexts.prod.env]\nSTRIPE = "sk_live_abc123"\n',
        "credential",
    )


def test_secret_in_top_level_env_rejected():
    _reject(
        '[metadata]\nid="a"\n[env]\nDB = "postgres://u:p@host/db"\n',
        "credential",
    )


def test_credential_in_server_address_rejected():
    _reject(
        '[metadata]\nid="a"\n[contexts.prod]\nserver="ssh://root:hunter2@h"\n',
        "credential",
    )


def test_wildcard_host_in_context_domains_rejected():
    _reject(
        '[metadata]\nid="a"\n[contexts.prod]\nserver="ssh://root@h"\n'
        '[contexts.prod.domains]\nlist = ["_", "myapp.com"]\n',
        "catch-all",
    )


def test_context_env_hostname_and_domains_mutually_exclusive():
    # A context may not set both [contexts.<n>.domains] and HOST_NAME in its env.
    # ("myapp.com" is not secret-shaped, so it clears the credential tripwire and
    # reaches validate_domains_vs_env_hostname as intended.)
    _reject(
        '[metadata]\nid="a"\n[contexts.prod]\nserver="ssh://root@h"\n'
        '[contexts.prod.domains]\nlist = ["myapp.com"]\n'
        '[contexts.prod.env]\nHOST_NAME = "myapp.com"\n',
        "HOST_NAME",
    )


def test_invalid_context_name_rejected():
    _reject(
        '[metadata]\nid="a"\n[contexts."has space"]\nserver="ssh://root@h"\n',
        "Invalid context name",
    )


def test_non_secret_connection_url_without_creds_allowed():
    # A URL with no embedded credentials is fine — only `user:pass@` trips it.
    cfg = Hop3Config.from_str(
        '[metadata]\nid="a"\n[env]\nREDIS = "redis://localhost:6379"\n'
    )
    assert cfg.env["REDIS"] == "redis://localhost:6379"


def test_context_app_inherits_when_absent():
    cfg = Hop3Config.from_str(
        '[metadata]\nid="myapp"\n[contexts.prod]\nserver="ssh://root@h"\n'
    )
    assert cfg.app_id == "myapp"
