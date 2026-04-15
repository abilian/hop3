# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the app-scoped command set (ADR 036 D7)."""

from __future__ import annotations

from hop3_cli.core.app_scope import APP_SCOPED_COMMANDS, is_app_scoped


def test_top_level_verbs_are_app_scoped() -> None:
    for verb in ("deploy", "logs", "run", "restart", "status", "ps", "scale", "ssh", "open"):
        scoped, n = is_app_scoped([verb])
        assert scoped, f"{verb!r} should be app-scoped"
        assert n == 1


def test_app_namespace_verbs_are_app_scoped() -> None:
    for verb in ("destroy", "show", "ping", "logs", "build-logs", "start", "stop",
                 "restart", "env", "debug", "sbom"):
        scoped, n = is_app_scoped(["app", verb])
        assert scoped, f"app {verb} should be app-scoped"
        assert n == 2


def test_config_namespace_is_app_scoped() -> None:
    for verb in ("show", "get", "set", "unset", "live"):
        scoped, n = is_app_scoped(["config", verb])
        assert scoped
        assert n == 2


def test_backup_create_is_app_scoped() -> None:
    scoped, n = is_app_scoped(["backup", "create"])
    assert scoped
    assert n == 2


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
