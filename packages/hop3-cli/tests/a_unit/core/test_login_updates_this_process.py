# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A login has to be visible to the rest of its own invocation.

`record_server_login` wrote the context to disk, but this process had already
resolved its connection before that — so everything running afterwards still
saw the pre-login answer. The cache refresh that runs on the back of a login
asked `get_api_url()` and was told "API URL not configured", printed one line
under "Signed in to ssh://root@host as admin", about the very server it had
just signed in to. Reported from a real run against hop3-dev.abilian.com.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local import completion_cmd, login_cmd
from hop3_cli.config import get_config

SERVER = "ssh://root@hop3-dev.example.com"


@pytest.fixture
def config(monkeypatch):
    """A real Config on an isolated config dir, with the network step stubbed."""
    # Imported inside `record_server_login`, so it is patched at its source.
    monkeypatch.setattr(completion_cmd, "refresh_caches_after_login", lambda _cfg: None)
    return get_config()


def test_the_server_just_recorded_is_the_one_this_process_resolves(config):
    login_cmd.record_server_login(config, SERVER, "tok")

    assert config.get_api_url() == SERVER


def test_the_cli_no_longer_reports_itself_unconfigured(config):
    """What the cache refresh asked, one line after a successful login."""
    login_cmd.record_server_login(config, SERVER, "tok")

    assert config.is_configured()


def test_the_bootstrap_route_travels_with_it(config):
    """`set_active_bootstrap` is wired from the same resolution as the server."""
    login_cmd.record_server_login(
        config, "https://hop3-dev.example.com", "tok", bootstrap=SERVER
    )

    assert config.get_bootstrap_target() == "root@hop3-dev.example.com"


def test_the_refresh_runs_with_the_server_already_resolved(config, monkeypatch):
    """Ordering is the whole bug: the refresh must not run before the update."""
    seen: list[str | None] = []
    monkeypatch.setattr(
        completion_cmd,
        "refresh_caches_after_login",
        lambda cfg: seen.append(cfg.get_api_url()),
    )

    login_cmd.record_server_login(config, SERVER, "tok")

    assert seen == [SERVER]
