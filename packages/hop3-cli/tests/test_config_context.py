# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Legacy config.toml connection read-fallback (ADR 042 r2).

config.toml ``[contexts.*]`` is no longer written: deploy environments live in
the app's ``hop3.toml`` and bearer tokens live in the per-server credential
store. What remains here is the one-release *read* fallback so an un-migrated
config.toml still resolves a connection until the startup migration drains it:

- ``Context.from_dict`` reads either the ``url``/``token`` or the legacy
  ``api_url``/``api_token`` spelling;
- the current-context pointer is read from ``[cli].current_context`` (with the
  legacy top-level ``current_context`` as a fallback).
"""

from __future__ import annotations

from hop3_cli.config import Context


# ---- connection field read (url/token, with legacy api_url/api_token) ------
def test_from_dict_prefers_url_token() -> None:
    c = Context.from_dict(
        "prod",
        {
            "url": "https://new",
            "token": "N",
            "api_url": "https://old",
            "api_token": "O",
        },
    )
    assert c.api_url == "https://new"
    assert c.api_token == "N"


def test_from_dict_reads_legacy_api_keys() -> None:
    c = Context.from_dict("prod", {"api_url": "https://legacy", "api_token": "L"})
    assert c.api_url == "https://legacy"
    assert c.api_token == "L"


# ---- current-context pointer read (cli over legacy top-level) --------------
def test_get_current_context_name_prefers_cli_over_legacy() -> None:
    from hop3_cli.config import Config  # noqa: PLC0415

    cfg = Config(
        data={
            "contexts": {"a": {"url": "x"}, "b": {"url": "y"}},
            "cli": {"current_context": "b"},
            "current_context": "a",  # stale legacy mirror
        }
    )
    assert cfg.get_current_context_name() == "b"


def test_get_current_context_name_falls_back_to_legacy_pointer() -> None:
    from hop3_cli.config import Config  # noqa: PLC0415

    cfg = Config(data={"contexts": {"a": {"url": "x"}}, "current_context": "a"})
    assert cfg.get_current_context_name() == "a"


# ---- the read fallback flows through get_api_url / get_api_token -----------
def test_legacy_context_resolves_connection_when_no_active_or_default() -> None:
    from hop3_cli.config import Config  # noqa: PLC0415

    cfg = Config(
        data={
            "contexts": {"default": {"api_url": "https://legacy", "api_token": "L"}},
            "current_context": "default",
        }
    )
    assert cfg.get_api_url() == "https://legacy"
    assert cfg.get_api_token() == "L"
    assert cfg.is_configured() is True
    assert cfg.is_authenticated() is True
