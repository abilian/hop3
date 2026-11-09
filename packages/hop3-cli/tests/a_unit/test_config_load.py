# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Config loading must fail loud on a malformed file (not silently return empty)."""

from __future__ import annotations

import pytest
from hop3_cli.config import Config
from hop3_cli.exceptions import ConfigError


def test_malformed_config_file_raises(tmp_path):
    """A malformed config.toml aborts loudly rather than masquerading as empty."""
    bad = tmp_path / "config.toml"
    bad.write_text('server = "unterminated\n')  # unterminated string -> invalid TOML

    with pytest.raises(ConfigError, match="Malformed config file"):
        Config.from_toml_file(bad)


def test_missing_config_file_uses_defaults(tmp_path):
    """A missing file is fine: defaults, not an error."""
    cfg = Config.from_toml_file(tmp_path / "config.toml")

    assert cfg.data == {}


def test_int_setting_from_environment_is_an_int(monkeypatch):
    """`HOP3_SSH_PORT=2222` reads as the int the caller's default promises."""
    monkeypatch.setenv("HOP3_SSH_PORT", "2222")

    assert Config().get("ssh_port", 22) == 2222


def test_int_setting_that_is_not_a_number_is_refused(monkeypatch):
    monkeypatch.setenv("HOP3_SSH_PORT", "twenty-two")

    with pytest.raises(ConfigError, match="HOP3_SSH_PORT must be an integer"):
        Config().get("ssh_port", 22)
