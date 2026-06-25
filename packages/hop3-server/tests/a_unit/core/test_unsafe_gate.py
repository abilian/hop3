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


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all three env vars the gate touches before each test."""
    monkeypatch.delenv("HOP3_UNSAFE", raising=False)
    monkeypatch.delenv("HOP3_UNSAFE_ACK", raising=False)
    monkeypatch.delenv("MODE", raising=False)
    return monkeypatch


@pytest.fixture(autouse=True)
def _restore_unsafe_snapshot():
    """The gate re-grounds the module-level config.HOP3_UNSAFE snapshot; restore
    it after each test so re-grounding can't leak across the suite."""

    original = cfg.HOP3_UNSAFE
    yield
    cfg.HOP3_UNSAFE = original


def test_production_force_regrounds_module_snapshot(clean_env) -> None:
    """The forced-off policy must reach config.HOP3_UNSAFE — the snapshot the
    auth guards actually read — not just os.environ (regression for a silent
    full-auth bypass in production)."""

    clean_env.setenv("HOP3_UNSAFE", "true")
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "production")

    enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"
    assert cfg.HOP3_UNSAFE is False  # what auth_guard reads


def test_dev_passthrough_regrounds_snapshot_true(clean_env) -> None:
    """In development the bypass really is on — and the snapshot reflects it."""

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


@pytest.mark.parametrize("truthy", ["true", "TRUE", "1", "yes", "on"])
def test_unsafe_accepts_common_truthy_spellings(clean_env, truthy: str, caplog) -> None:
    clean_env.setenv("HOP3_UNSAFE", truthy)
    clean_env.setenv("HOP3_UNSAFE_ACK", ACK_VALUE)
    clean_env.setenv("MODE", "production")
    with caplog.at_level(logging.CRITICAL):
        enforce_unsafe_mode_policy()

    assert os.environ["HOP3_UNSAFE"] == "false"


@pytest.mark.parametrize("falsy", ["", "false", "0", "no", "off"])
def test_unsafe_falsy_values_are_noops(clean_env, falsy: str) -> None:
    clean_env.setenv("HOP3_UNSAFE", falsy)
    # No ACK, no MODE — must not raise.
    enforce_unsafe_mode_policy()
