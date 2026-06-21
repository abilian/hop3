# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the app-scoped command set (ADR 036 D7)."""

from __future__ import annotations

from hop3_cli.core.app_scope import APP_SCOPED_COMMANDS, is_app_scoped


def test_top_level_verbs_are_app_scoped() -> None:
    for verb in (
        "deploy",
        "logs",
        "run",
        "restart",
        "status",
        "ps",
        "scale",
        "ssh",
        "open",
    ):
        scoped, n = is_app_scoped([verb])
        assert scoped, f"{verb!r} should be app-scoped"
        assert n == 1


def test_app_namespace_verbs_are_app_scoped() -> None:
    # Mirrors the `app` command tuples registered server-side. The detail
    # verb is `status` (not the old `show`): `hop3 app status` must resolve
    # an implicit app like its siblings.
    for verb in (
        "destroy",
        "status",
        "ping",
        "logs",
        "build-logs",
        "start",
        "stop",
        "restart",
        "env",
        "debug",
        "sbom",
    ):
        scoped, n = is_app_scoped(["app", verb])
        assert scoped, f"app {verb} should be app-scoped"
        assert n == 2


def test_stale_app_show_is_not_scoped() -> None:
    """`app show` was renamed to `app status`; the dead name must not linger."""
    scoped, _ = is_app_scoped(["app", "show"])
    assert not scoped


def test_config_namespace_is_app_scoped() -> None:
    for verb in ("show", "get", "set", "unset", "live"):
        scoped, n = is_app_scoped(["config", verb])
        assert scoped
        assert n == 2


def test_backup_create_is_app_scoped() -> None:
    scoped, n = is_app_scoped(["backup", "create"])
    assert scoped
    assert n == 2


def test_domain_namespace_is_app_scoped() -> None:
    # `domain` reads the app from --app and has no positional fallback, so it
    # must be app-scoped (CLI injects --app) like env/app — otherwise a bare
    # `hop3 domain list` from a project couldn't resolve the app. The `domains`
    # alias must scope identically.
    for verb in ("add", "remove", "set", "clear", "list"):
        scoped, n = is_app_scoped(["domain", verb])
        assert scoped, f"domain {verb} should be app-scoped"
        assert n == 2
        scoped_alias, _ = is_app_scoped(["domains", verb])
        assert scoped_alias, f"domains {verb} should be app-scoped"


def test_bare_domain_is_not_app_scoped() -> None:
    """Bare `hop3 domain` shows namespace help; it must not demand an app."""
    scoped, _ = is_app_scoped(["domain"])
    assert not scoped


def test_apps_list_is_not_app_scoped() -> None:
    """`apps` (list-everything) is not app-scoped."""
    scoped, _ = is_app_scoped(["apps"])
    assert not scoped


def test_help_is_not_app_scoped() -> None:
    scoped, _ = is_app_scoped(["help"])
    assert not scoped


def test_version_is_not_app_scoped() -> None:
    scoped, _ = is_app_scoped(["version"])
    assert not scoped


def test_empty_is_not_app_scoped() -> None:
    scoped, n = is_app_scoped([])
    assert not scoped
    assert n == 0


def test_longest_prefix_match() -> None:
    """`config set FOO=bar` should match ("config", "set"), not ("config",)."""
    scoped, n = is_app_scoped(["config", "set", "FOO=bar"])
    assert scoped
    assert n == 2


def test_app_scoped_set_has_no_empty_tuple() -> None:
    assert () not in APP_SCOPED_COMMANDS
    assert len(APP_SCOPED_COMMANDS) > 0
