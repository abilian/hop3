# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for M8: user config, --no-input, dynamic app completion."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hop3_cli.commands.local import completion_cmd
from hop3_cli.core.alias_registry import load_user_aliases_with_diagnostics
from hop3_cli.main import run_command_from_args
from hop3_cli.rpc.responses import _app_not_found_suggestion
from hop3_cli.ui.prompts import (
    NoInputError,
    is_no_input,
    require_input_allowed,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---- M8.1: alias config diagnostics ----


def test_missing_config_yields_empty_with_no_diags() -> None:
    aliases, diags = load_user_aliases_with_diagnostics(None)
    assert aliases == []
    assert diags.parse_error is None
    assert diags.rejected == []


def test_nonexistent_file_yields_empty_with_no_diags(tmp_path: Path) -> None:
    aliases, diags = load_user_aliases_with_diagnostics(tmp_path / "nope.toml")
    assert aliases == []
    assert diags.parse_error is None


def test_toml_parse_error_is_reported(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    f.write_text("not [valid] toml = at all", encoding="utf-8")
    aliases, diags = load_user_aliases_with_diagnostics(f)
    assert aliases == []
    assert diags.parse_error is not None
    assert "TOML parse error" in diags.parse_error


def test_non_table_aliases_section_is_reported(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    f.write_text('aliases = "not-a-table"', encoding="utf-8")
    aliases, diags = load_user_aliases_with_diagnostics(f)
    assert aliases == []
    assert diags.parse_error is not None
    assert "must be a table" in diags.parse_error


def test_empty_expansion_is_rejected_with_reason(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    f.write_text('[aliases]\nfoo = ""\n', encoding="utf-8")
    aliases, diags = load_user_aliases_with_diagnostics(f)
    assert aliases == []
    assert diags.rejected == [("foo", "expansion is empty")]


def test_non_string_expansion_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    f.write_text("[aliases]\nfoo = 42\n", encoding="utf-8")
    aliases, diags = load_user_aliases_with_diagnostics(f)
    assert aliases == []
    assert len(diags.rejected) == 1
    assert diags.rejected[0][0] == "foo"
    assert "expansion must be a string" in diags.rejected[0][1]


def test_valid_aliases_load_cleanly(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    f.write_text(
        '[aliases]\npg = "addon postgres"\nll = "app list"\n', encoding="utf-8"
    )
    aliases, diags = load_user_aliases_with_diagnostics(f)
    assert {a.source_token for a in aliases} == {"pg", "ll"}
    assert diags.parse_error is None
    assert diags.rejected == []


# ---- M8.2: --no-input plumbing ----


@pytest.fixture(autouse=True)
def _clear_no_input_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_NO_INPUT", raising=False)


def test_is_no_input_reads_env() -> None:
    assert is_no_input() is False
    os.environ["HOP3_NO_INPUT"] = "1"
    try:
        assert is_no_input() is True
    finally:
        del os.environ["HOP3_NO_INPUT"]


def test_require_input_allowed_raises_when_no_input_set() -> None:
    os.environ["HOP3_NO_INPUT"] = "1"
    try:
        with pytest.raises(NoInputError, match="would require an interactive prompt"):
            require_input_allowed("confirmation")
    finally:
        del os.environ["HOP3_NO_INPUT"]


def test_require_input_allowed_noop_when_unset() -> None:
    # No exception when the env var is absent.
    require_input_allowed("confirmation")


def test_no_input_flag_sets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_flags + main wiring should expose --no-input via the env var."""
    monkeypatch.delenv("HOP3_NO_INPUT", raising=False)

    captured = {}

    def fake_load_config():
        captured["no_input"] = is_no_input()

        class _Stub:
            def is_configured(self):
                return False

            def is_authenticated(self):
                return False

            def set_context_override(self, _):
                pass

            def get_current_context_name(self):
                return None

            def get_current_context(self):
                return None

            def get_api_url(self):
                return None

        return _Stub()

    with (
        patch("hop3_cli.main.load_config", side_effect=fake_load_config),
        patch("hop3_cli.main._apply_aliases", side_effect=lambda args, *a, **kw: args),
        patch("hop3_cli.main.is_local_command", return_value=True),
        patch("hop3_cli.main.handle_local_command", return_value=True),
    ):
        run_command_from_args(["--no-input", "help"])

    assert captured["no_input"] is True


# ---- M8.3: app-name cache ----


def test_read_apps_cache_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completion_cmd, "APPS_CACHE_TXT", tmp_path / "apps.txt")
    assert completion_cmd.read_apps_cache() == []


def test_write_and_read_apps_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(completion_cmd, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(completion_cmd, "APPS_CACHE_TXT", cache_dir / "apps.txt")

    completion_cmd.write_apps_cache(["alpha", "beta", "gamma"])
    assert completion_cmd.read_apps_cache() == ["alpha", "beta", "gamma"]


def test_app_not_found_suggestion_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completion_cmd, "APPS_CACHE_TXT", tmp_path / "apps.txt")
    tmp_path.joinpath("apps.txt").write_text(
        "acme-dev\nacme-prod\nuptime-kuma\n", encoding="utf-8"
    )

    hint = _app_not_found_suggestion("App 'acme-dv' not found")
    assert hint is not None
    assert "acme-dev" in hint


def test_app_not_found_suggestion_empty_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completion_cmd, "APPS_CACHE_TXT", tmp_path / "apps.txt")
    assert _app_not_found_suggestion("App 'foo' not found") is None


def test_app_not_found_suggestion_no_match_in_message() -> None:
    assert _app_not_found_suggestion("Something unrelated") is None
