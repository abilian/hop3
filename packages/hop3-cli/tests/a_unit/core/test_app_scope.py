# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the app-scoped command set (ADR 036 D7)."""

from __future__ import annotations

from hop3_cli.core.app_scope import APP_SCOPED_COMMANDS, app_scope_depth


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
        assert app_scope_depth([verb]) == 1, f"{verb!r} should be app-scoped"


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
        "debug",
        "sbom",
        "credentials",  # ADR 056 — `hop3 app credentials --app X` must forward --app
    ):
        assert app_scope_depth(["app", verb]) == 2, f"app {verb} should be app-scoped"


def test_removed_app_env_is_not_scoped() -> None:
    """
    `app env` was removed (use `env show --sources`); it must not linger as
    an app-scoped verb.
    """
    assert not app_scope_depth(["app", "env"])


def test_stale_app_show_is_not_scoped() -> None:
    """`app show` was renamed to `app status`; the dead name must not linger."""
    assert not app_scope_depth(["app", "show"])


def test_config_namespace_is_app_scoped() -> None:
    for verb in ("show", "get", "set", "unset", "live"):
        assert app_scope_depth(["config", verb]) == 2


def test_ps_scale_gets_the_app_after_its_full_name() -> None:
    """`ps --app x scale web=2` ran `ps` with stray arguments."""
    assert app_scope_depth(["ps", "scale", "web=2"]) == 2


def test_backup_create_is_app_scoped() -> None:
    assert app_scope_depth(["backup", "create"]) == 2


def test_domain_namespace_is_app_scoped() -> None:
    # `domain` reads the app from --app and has no positional fallback, so it
    # must be app-scoped (CLI injects --app) like env/app — otherwise a bare
    # `hop3 domain list` from a project couldn't resolve the app. The `domains`
    # alias must scope identically.
    for verb in ("add", "remove", "set", "clear", "list"):
        assert app_scope_depth(["domain", verb]) == 2, (
            f"domain {verb} should be app-scoped"
        )
        assert app_scope_depth(["domains", verb]), (
            f"domains {verb} should be app-scoped"
        )


def test_bare_domain_is_not_app_scoped() -> None:
    """Bare `hop3 domain` shows namespace help; it must not demand an app."""
    assert not app_scope_depth(["domain"])


def test_apps_list_is_not_app_scoped() -> None:
    """`apps` (list-everything) is not app-scoped."""
    assert not app_scope_depth(["apps"])


def test_help_is_not_app_scoped() -> None:
    assert not app_scope_depth(["help"])


def test_version_is_not_app_scoped() -> None:
    assert not app_scope_depth(["version"])


def test_empty_is_not_app_scoped() -> None:
    assert app_scope_depth([]) == 0


def test_longest_prefix_match() -> None:
    """`config set FOO=bar` should match ("config", "set"), not ("config",)."""
    assert app_scope_depth(["config", "set", "FOO=bar"]) == 2


def test_app_scoped_set_has_no_empty_tuple() -> None:
    assert () not in APP_SCOPED_COMMANDS
    assert len(APP_SCOPED_COMMANDS) > 0
