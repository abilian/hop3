# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the alias mechanism (ADR 036 D9, M3)."""

from __future__ import annotations

from pathlib import Path

from hop3_cli.core.alias_registry import (
    AliasRegistry,
    build_registry,
    build_subcommand_index,
    load_user_aliases_from_config,
    resolve_aliases,
)
from hop3_cli.core.aliases import CORE_ALIASES, Alias

# ---- Core alias table ----


def test_core_aliases_contain_expected_entries() -> None:
    tokens = {a.source_token for a in CORE_ALIASES}
    # Per command catalog
    assert {"apps", "addons", "plugins", "env", "whoami"} <= tokens


def test_core_aliases_have_tuple_expansions() -> None:
    for alias in CORE_ALIASES:
        assert isinstance(alias.expansion, tuple)
        assert all(isinstance(t, str) for t in alias.expansion)
        assert len(alias.expansion) >= 1


def test_login_logout_are_not_aliases() -> None:
    """`login`/`logout` are LOCAL commands with custom SSH flows, not aliases."""
    tokens = {a.source_token for a in CORE_ALIASES}
    assert "login" not in tokens
    assert "logout" not in tokens


# ---- Registry build ----


def test_registry_starts_with_core_only() -> None:
    r = build_registry()
    for alias in CORE_ALIASES:
        assert r.find(alias.source_token) is alias


def test_user_alias_adds_when_no_collision() -> None:
    user = [Alias("ll", ("app", "list"), "user", origin_detail="/tmp/test")]
    r = build_registry(user_aliases=user)
    assert r.find("ll") is user[0]


def test_user_alias_skipped_on_collision_with_core() -> None:
    # `env` is in core — user tries to shadow
    user = [Alias("env", ("custom", "env"), "user")]
    r = build_registry(user_aliases=user)
    # Core entry wins
    found = r.find("env")
    assert found is not None
    assert found.origin == "built-in"
    # User entry is skipped with a reason
    assert any(tok == "env" for tok, _ in r.skipped)


def test_plugin_alias_skipped_on_collision_with_core() -> None:
    plugins = [Alias("apps", ("custom", "apps"), "plugin")]
    r = build_registry(plugin_aliases=plugins)
    assert r.find("apps").origin == "built-in"
    assert any(tok == "apps" for tok, _ in r.skipped)


def test_user_alias_skipped_on_collision_with_plugin() -> None:
    plugins = [Alias("drain", ("drain",), "plugin")]
    user = [Alias("drain", ("my", "drain"), "user")]
    r = build_registry(plugin_aliases=plugins, user_aliases=user)
    assert r.find("drain").origin == "plugin"
    assert any(tok == "drain" for tok, _ in r.skipped)


# ---- User alias loading ----


def test_load_user_aliases_from_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[aliases]
ll = "app list"
pg = "addon postgres"
""")
    aliases = load_user_aliases_from_config(config_file)
    by_token = {a.source_token: a for a in aliases}
    assert by_token["ll"].expansion == ("app", "list")
    assert by_token["pg"].expansion == ("addon", "postgres")
    assert all(a.origin == "user" for a in aliases)


def test_load_user_aliases_missing_file_ok(tmp_path: Path) -> None:
    assert load_user_aliases_from_config(tmp_path / "no-such-file.toml") == []


def test_load_user_aliases_no_section_ok(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[other]\nkey = 1\n")
    assert load_user_aliases_from_config(config_file) == []


def test_load_user_aliases_malformed_toml_ok(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("not valid toml [[[")
    assert load_user_aliases_from_config(config_file) == []


# ---- Resolution ----


def test_resolve_fires_on_bare_alias() -> None:
    r = build_registry()
    out, fired = resolve_aliases(["apps"], r)
    assert fired is not None
    assert fired.source_token == "apps"
    assert out == ["app", "list"]


def test_resolve_passes_through_non_alias() -> None:
    r = build_registry()
    out, fired = resolve_aliases(["deploy", "myapp"], r)
    assert fired is None
    assert out == ["deploy", "myapp"]


def test_resolve_forwards_trailing_args() -> None:
    r = build_registry()
    out, fired = resolve_aliases(["env", "myapp"], r)
    assert out == ["config", "show", "myapp"]
    assert fired is not None


def test_resolve_fires_with_flag_after_alias() -> None:
    """Flags after the alias are forwarded untouched."""
    r = build_registry()
    out, fired = resolve_aliases(["apps", "--json"], r)
    assert out == ["app", "list", "--json"]
    assert fired is not None


def test_resolve_blocks_on_subcommand_collision() -> None:
    """`hop3 addons create foo` should NOT expand `addons` -> `addon list`.

    The user most likely meant the singular namespace form.
    """
    r = build_registry()
    index = {"addon": {"list", "create", "destroy"}, "app": {"list", "create"}}
    out, fired = resolve_aliases(
        ["addons", "create", "foo"], r, known_subcommands_of_namespace=index
    )
    assert fired is None
    assert out == ["addons", "create", "foo"]


def test_resolve_fires_when_next_token_not_a_subcommand() -> None:
    """`addons some-value` — `some-value` isn't a known subcommand, so expand."""
    r = build_registry()
    index = {"addon": {"list", "create"}}
    out, fired = resolve_aliases(
        ["addons", "--verbose"], r, known_subcommands_of_namespace=index
    )
    # --verbose isn't a positional subcommand, so alias fires.
    assert fired is not None
    assert out == ["addon", "list", "--verbose"]


def test_resolve_empty_args() -> None:
    r = build_registry()
    out, fired = resolve_aliases([], r)
    assert fired is None
    assert out == []


# ---- build_subcommand_index ----


def test_build_subcommand_index_basic() -> None:
    names = ["app list", "app create", "addon show", "apps", "backup create"]
    idx = build_subcommand_index(names)
    assert idx["app"] == {"list", "create"}
    assert idx["addon"] == {"show"}
    assert idx["backup"] == {"create"}
    # Single-token names do not contribute.
    assert "apps" not in idx


# ---- AliasRegistry dataclass ----


def test_registry_empty_has_no_aliases() -> None:
    r = AliasRegistry()
    assert r.find("anything") is None
