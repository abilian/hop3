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
