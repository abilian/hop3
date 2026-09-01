# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The TUI inherits hop3-cli's configuration, so it has to look where hop3-cli looks.

It used to guess a config path per platform and guessed wrong on macOS: hop3-cli
resolves `~/.config/hop3-cli/config.toml` via `platformdirs`, while the TUI looked in
`~/Library/Application Support/hop3-cli/`. Finding nothing, it fell back to its own
default server — `http://localhost:5000` — and reported whatever else was listening
there as a Hop3 error. The user's bug report was "http error 404" from a stray
Werkzeug app.

Both halves are pinned here: the path must equal hop3-cli's, and there must be no
default server to fall back to.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from hop3_cli.core import paths as cli_paths
from hop3_cli.core.paths import config_dir as cli_config_dir
from hop3_tui.app import Hop3TUI
from hop3_tui.config import CLI_APP_NAME, TUIConfig


def test_the_tui_looks_where_hop3_cli_keeps_its_config(monkeypatch, tmp_path: Path):
    """Compared against hop3-cli's own resolver, not against a hardcoded path."""
    monkeypatch.delenv("HOP3_CONFIG_DIR", raising=False)
    expected = cli_config_dir() / "config.toml"

    # `_find_cli_config_file` returns None unless the file exists, so point both at
    # a directory we control and assert they agree on where that is.
    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text('api_url = "http://example.test:8000"\n')

    assert TUIConfig._find_cli_config_file() == tmp_path / "config.toml"
    assert cli_config_dir() / "config.toml" == tmp_path / "config.toml"
    # And with the override gone, both name the same real location.
    monkeypatch.delenv("HOP3_CONFIG_DIR")
    assert cli_config_dir() / "config.toml" == expected


def test_the_app_name_matches_the_one_hop3_cli_registers():
    """A drifted app name would silently stop the TUI inheriting anything."""
    assert CLI_APP_NAME == cli_paths.APP_NAME


def test_there_is_no_default_server_to_fall_back_to():
    """hop3-cli has no default api_url either: unconfigured must be detectable.

    A default is not harmless here. It pointed at localhost:5000, where whatever
    else the developer was running answered, and the TUI reported that stranger's
    404 as its own.
    """
    assert TUIConfig().server_url == ""


def test_a_flat_api_url_is_inherited(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'api_url = "http://example.test:8000"\napi_token = "t"\n'
    )

    config = TUIConfig._load_from_cli_config(tmp_path / "config.toml", TUIConfig())

    assert config.server_url == "http://example.test:8000"
    assert config.auth_token == "t"


def test_the_active_context_wins_over_the_flat_url(tmp_path: Path):
    """hop3-cli resolves the context's server ahead of `api_url`; so must the TUI."""
    path = tmp_path / "config.toml"
    path.write_text(
        'api_url = "http://ignored.test:8000"\n'
        "[cli]\n"
        'default_context = "prod"\n'
        "[contexts.prod]\n"
        'server = "https://prod.test"\n'
    )

    config = TUIConfig._load_from_cli_config(path, TUIConfig())

    assert config.server_url == "https://prod.test"


def test_an_ssh_context_is_reported_rather_than_silently_bypassed(tmp_path: Path):
    """The TUI has no SSH tunnel, so an ssh:// target is not a URL it can use.

    Reading past it to `api_url` would point the TUI at a different server from the
    one `hop3` talks to — the same class of quiet disagreement as the path bug.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        'api_url = "http://localhost:8000"\n'
        "[cli]\n"
        'default_context = "prod"\n'
        "[contexts.prod]\n"
        'server = "ssh://root@prod.test"\n'
    )

    config = TUIConfig._load_from_cli_config(path, TUIConfig())

    assert config.cli_ssh_target == "ssh://root@prod.test"
    assert config.server_url == "", "must not silently use a different server"


def test_the_unconfigured_error_names_the_ssh_target_and_the_way_out():
    config = TUIConfig(cli_ssh_target="ssh://root@prod.test")
    message = Hop3TUI(config).api_client.unconfigured_hint

    assert "ssh://root@prod.test" in message
    assert "SSH tunnel" in message


@pytest.mark.parametrize("sample", ["config.toml"])
def test_the_users_own_config_shape_is_one_we_understand(sample: str):
    """A smoke check that the real file, if present, parses the way we expect."""
    path = cli_config_dir() / sample
    if not path.exists():
        pytest.skip(f"no hop3-cli config at {path} on this machine")

    data = tomllib.loads(path.read_text())

    assert isinstance(data, dict)
