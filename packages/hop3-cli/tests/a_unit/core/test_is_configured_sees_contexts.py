# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
``is_configured`` reads a global context's server (ADR 042 r2).

A global context is ``[contexts.<name>].server`` in config.toml — an address,
with the token in the credential store. ``is_configured`` predated that shape
and looked for a ``url``/``api_url`` key instead, so on a migrated config it
answered False for every context on the machine.

That is only invisible to RPC commands, because ``_wire_active_server`` sets
``_active_server`` before they check. Everything dispatched *earlier* got the
wrong answer: offline help (``hop3 --context prod app --help`` printed "Not
connected to a server yet" while ``system info`` reached the same server),
``completion refresh``, ``login`` and ``settings show``.
"""

from __future__ import annotations

import pytest
from hop3_cli.config import Config

MIGRATED = {
    "contexts": {
        "prod": {"server": "ssh://root@prod.example.com"},
        "dev": {"server": "https://dev.example.com"},
    },
    "cli": {"default_context": "dev"},
}


@pytest.fixture(autouse=True)
def _no_ambient_server(monkeypatch) -> None:
    """The env vars are step 1 and 2 and would answer True on their own."""
    for var in ("HOP3_DEV_MODE", "HOP3_API_URL", "HOP3_CONTEXT"):
        monkeypatch.delenv(var, raising=False)


def test_the_context_named_by_the_flag_counts_as_configured() -> None:
    """`hop3 --context prod app --help` is the reported failure."""
    config = Config(data=MIGRATED)
    config.set_context_override("prod")

    assert config.is_configured() is True


def test_the_stored_default_context_counts_as_configured() -> None:
    """Bare `hop3 help` has no override and must not fall through either."""
    assert Config(data=MIGRATED).is_configured() is True


def test_an_environment_context_counts(monkeypatch) -> None:
    monkeypatch.setenv("HOP3_CONTEXT", "prod")

    assert Config(data=MIGRATED).is_configured() is True


def test_a_context_with_no_server_does_not_count() -> None:
    """An empty address is not a server; the predicate must stay a gate."""
    config = Config(data={"contexts": {"prod": {"server": ""}}})
    config.set_context_override("prod")

    assert config.is_configured() is False


def test_an_unknown_context_name_does_not_count() -> None:
    config = Config(data=MIGRATED)
    config.set_context_override("nope")

    assert config.is_configured() is False


def test_an_empty_config_is_still_unconfigured() -> None:
    """The offline-help path has to keep working for a first-run CLI."""
    assert Config(data={}).is_configured() is False
