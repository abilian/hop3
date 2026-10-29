# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HOP3_UNSAFE safety interlock."""

from __future__ import annotations

import logging
import os

import pytest

import hop3.config as cfg
from hop3.core.unsafe_gate import (
    ACK_VALUE,
    UnsafeModeError,
    enforce_unsafe_mode_policy,
)
from hop3.lib.config import Config as ConfigLoader


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all three env vars the gate touches before each test."""
    monkeypatch.delenv("HOP3_UNSAFE", raising=False)
    monkeypatch.delenv("HOP3_UNSAFE_ACK", raising=False)
    monkeypatch.delenv("MODE", raising=False)
    return monkeypatch


def test_production_force_reaches_the_live_setting(clean_env) -> None:
    """
    The forced-off policy must reach config.HOP3_UNSAFE, the value the auth
    guards read (regression for a silent full-auth bypass in production).
    """

    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "production")

    enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"
    assert cfg.HOP3_UNSAFE is False  # what the role guards read


def test_dev_passthrough_keeps_the_bypass_on(clean_env) -> None:
    """In development the bypass really is on, as the guards read it."""

    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "development")

    enforce_unsafe_mode_policy()

    assert cfg.HOP3_UNSAFE is True


def test_no_unsafe_requested_is_noop(clean_env) -> None:
    # HOP3_UNSAFE unset: gate does nothing, env stays clean.
    enforce_unsafe_mode_policy()

    assert "HOP3_UNSAFE" not in os.environ


def test_unsafe_requested_without_ack_refuses_to_boot(clean_env) -> None:
    clean_env.setenv("HOP3_UNSAFE", "true")
    with pytest.raises(UnsafeModeError, match="HOP3_UNSAFE_ACK"):
        enforce_unsafe_mode_policy()


def test_unsafe_requested_with_wrong_ack_refuses_to_boot(clean_env) -> None:
    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", "sure-i-understand")
    with pytest.raises(UnsafeModeError, match="HOP3_UNSAFE_ACK"):
        enforce_unsafe_mode_policy()


def test_unsafe_production_forced_off(clean_env, caplog) -> None:
    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "production")
    with caplog.at_level(logging.CRITICAL):
        enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"
    # Critical-level log fired.
    assert any("SECURITY" in r.message for r in caplog.records)


def test_unsafe_prod_alias_also_forced_off(clean_env, caplog) -> None:
    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "prod")
    with caplog.at_level(logging.CRITICAL):
        enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"


def test_unsafe_dev_with_ack_passes_through(clean_env) -> None:
    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "development")
    enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "true"


def test_unsafe_default_mode_is_production(clean_env, caplog) -> None:
    # No MODE env means the gate assumes production and forces off.
    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    with caplog.at_level(logging.CRITICAL):
        enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"


@pytest.mark.parametrize("truthy", ["true", "TRUE", "1"])
def test_unsafe_accepts_the_spellings_the_guards_accept(clean_env, truthy) -> None:
    clean_env.setenv("HOP3_UNSAFE", truthy)
    with pytest.raises(UnsafeModeError):
        enforce_unsafe_mode_policy()


@pytest.mark.parametrize("unparsable", ["yes", "on", "no", "off", ""])
def test_a_value_the_guards_cannot_parse_refuses_to_boot(clean_env, unparsable) -> None:
    """
    The gate parses ``HOP3_UNSAFE`` as the guards do. It used to accept
    ``yes``/``on`` while the guards raised on them, and to ignore ``no``.
    """
    clean_env.setenv("HOP3_UNSAFE", unparsable)
    with pytest.raises(ValueError, match="HOP3_UNSAFE"):
        enforce_unsafe_mode_policy()


@pytest.mark.parametrize("falsy", ["false", "FALSE", "0"])
def test_unsafe_falsy_values_are_noops(clean_env, falsy) -> None:
    clean_env.setenv("HOP3_UNSAFE", falsy)
    enforce_unsafe_mode_policy()  # no raise
    assert os.environ["HOP3_UNSAFE"] == falsy


def test_unsafe_set_in_the_config_file_needs_the_ack(clean_env, tmp_path) -> None:
    """
    ``HOP3_UNSAFE = true`` in hop3-server.toml reaches the auth guards, so it
    must meet the gate too. The gate used to read only the environment, and
    the file disabled authentication with no ACK and no production override.
    """
    config_file = tmp_path / "hop3-server.toml"
    config_file.write_text("HOP3_UNSAFE = true\n")
    previous = cfg.HopConfig.get_instance()
    cfg.HopConfig.set_instance(cfg.HopConfig(ConfigLoader(file=config_file)))
    try:
        assert cfg.HOP3_UNSAFE is True  # what the guards read
        with pytest.raises(UnsafeModeError, match="HOP3_UNSAFE_ACK"):
            enforce_unsafe_mode_policy()
    finally:
        cfg.HopConfig.set_instance(previous)


def test_unsafe_in_the_config_file_is_forced_off_in_production(
    clean_env, tmp_path
) -> None:
    config_file = tmp_path / "hop3-server.toml"
    config_file.write_text(f'HOP3_UNSAFE = true\nHOP3_UNSAFE_ACK = "{ACK_VALUE}"\n')
    previous = cfg.HopConfig.get_instance()
    cfg.HopConfig.set_instance(cfg.HopConfig(ConfigLoader(file=config_file)))
    try:
        enforce_unsafe_mode_policy()
        assert cfg.HOP3_UNSAFE is False  # the environment outranks the file
    finally:
        cfg.HopConfig.set_instance(previous)
