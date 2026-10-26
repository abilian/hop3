# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the main.py wiring of ADR 042 §D14 + §Deploy preview.

Covers the integration of `_check_project_mismatch`, `_forward_dry_run`,
`_handle_deploy_preview`, `_deploy_source_path`, `_matches_guarded_prefix`,
and `_compute_app_resolution`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_cli.commands.flags import CliFlags, parse_flags
from hop3_cli.config import Config
from hop3_cli.core.resolution import AppSource, ContextSource, resolve_context
from hop3_cli.core.target import Target
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import (
    _check_project_mismatch,
    _compute_app_resolution,
    _deploy_source_path,
    _forward_dry_run,
    _handle_deploy_preview,
    _matches_guarded_prefix,
)

# ============================================================================
# _matches_guarded_prefix
# ============================================================================


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["deploy"], ("deploy",)),
        (["deploy", "myapp"], ("deploy",)),
        (["restart", "myapp"], ("restart",)),
        (["config", "set", "myapp", "KEY=value"], ("config", "set")),
        (["app", "destroy", "myapp"], ("app", "destroy")),
        # Bare ``destroy`` is intentionally NOT in the list; aliases rewrite it.
        (["destroy", "myapp"], None),
        (["logs", "myapp"], None),
        (["status"], None),
        ([], None),
        # `config get` is not guarded (read-only).
        (["config", "get", "myapp", "KEY"], None),
    ],
)
def test_matches_guarded_prefix(argv, expected) -> None:
    assert _matches_guarded_prefix(argv) == expected


# ============================================================================
# _check_project_mismatch — the §D14 integration
# ============================================================================


def _flags(**overrides) -> CliFlags:
    """Construct CliFlags from defaults + overrides."""
    return CliFlags(**overrides)


class _Resolution:
    """
    Cheap stand-in for AppResolution: only needs .resolved, .app, .source, .kind.

    Default kind is ENV — the most common "guard should fire" case in
    these tests (env-var pointing at the wrong app from the wrong CWD).
    Tests that want CWD-rooted behavior pass kind explicitly.
    """

    def __init__(
        self,
        app: str | None,
        source: str = "$HOP3_APP",
        kind: AppSource = AppSource.ENV,
    ) -> None:
        self.app = app
        self.source = source
        self.kind = kind

    @property
    def resolved(self) -> bool:
        return bool(self.app)


def _write_hop3_toml(directory: Path, app_id: str) -> None:
    directory.joinpath("hop3.toml").write_text(f'[metadata]\nid = "{app_id}"\n')


def test_guard_skipped_when_app_unresolved(tmp_path: Path) -> None:
    _write_hop3_toml(tmp_path, "myapp")
    _check_project_mismatch(["deploy"], _flags(), _Resolution(None))  # must not raise


def test_guard_skipped_for_non_guarded_verb(tmp_path: Path) -> None:
    _write_hop3_toml(tmp_path, "myapp")
    with patch("hop3_cli.core.project_guard.Path.cwd", return_value=tmp_path):
        _check_project_mismatch(
            ["logs"], _flags(), _Resolution("other-app", "$HOP3_APP")
        )  # must not raise / sys.exit


def test_guard_fires_on_mismatch_with_env_var_source(tmp_path: Path) -> None:
    _write_hop3_toml(tmp_path, "myapp")
    with (
        patch("hop3_cli.core.project_guard.Path.cwd", return_value=tmp_path),
        patch(
            "hop3_cli.core.project_guard.Path.home",
            return_value=tmp_path.parent,
        ),
        pytest.raises(SystemExit) as exc,
    ):
        _check_project_mismatch(
            ["deploy"],
            _flags(),
            _Resolution("other-app", "$HOP3_APP"),
        )
    # ADR 042: refusal uses RESOLUTION_ERROR (3), NOT
    # CONFIRMATION_DECLINED (10). Scripts rely on the distinction.
    assert exc.value.code == ExitCode.RESOLUTION_ERROR


def test_guard_not_bypassed_by_yes_alone(tmp_path: Path) -> None:
    """
    Real-world incident: ``hop3 deploy -y`` from the wrong directory must
    NOT silently deploy. ``-y/--yes`` skips prompts; ``--force`` bypasses
    the §D14 guard. The two are not interchangeable.
    """
    _write_hop3_toml(tmp_path, "myapp")
    with (
        patch("hop3_cli.core.project_guard.Path.cwd", return_value=tmp_path),
        patch(
            "hop3_cli.core.project_guard.Path.home",
            return_value=tmp_path.parent,
        ),
        pytest.raises(SystemExit),
    ):
        _check_project_mismatch(
            ["deploy"],
            _flags(skip_confirm=True),  # -y / --yes
            _Resolution("other-app", "$HOP3_APP"),
        )


def test_guard_bypassed_by_force(tmp_path: Path) -> None:
    _write_hop3_toml(tmp_path, "myapp")
    with (
        patch("hop3_cli.core.project_guard.Path.cwd", return_value=tmp_path),
        patch(
            "hop3_cli.core.project_guard.Path.home",
            return_value=tmp_path.parent,
        ),
    ):
        # Must NOT raise — --force is the documented escape hatch.
        _check_project_mismatch(
            ["deploy"],
            _flags(force=True, skip_confirm=True),
            _Resolution("other-app", "$HOP3_APP"),
        )


def test_guard_not_fired_when_source_is_cwd_rooted(tmp_path: Path) -> None:
    _write_hop3_toml(tmp_path, "myapp")
    with (
        patch("hop3_cli.core.project_guard.Path.cwd", return_value=tmp_path),
        patch(
            "hop3_cli.core.project_guard.Path.home",
            return_value=tmp_path.parent,
        ),
    ):
        _check_project_mismatch(
            ["deploy"],
            _flags(),
            _Resolution(
                "myapp-staging",
                "hop3.toml [cli].app at /tmp/x",
                kind=AppSource.CLI_APP,
            ),
        )  # must not raise


# ============================================================================
# _forward_dry_run — the command gets its flag back
# ============================================================================


def test_dry_run_stays_with_the_client_for_deploy() -> None:
    assert _forward_dry_run(["deploy"], _flags(dry_run=True)) == ["deploy"]


def test_dry_run_is_forwarded_to_other_commands() -> None:
    """`system cleanup --dry-run` must preview, never prune for real."""
    argv = ["system", "cleanup"]
    assert _forward_dry_run(argv, _flags(dry_run=True)) == [*argv, "--dry-run"]


def test_no_dry_run_forwards_nothing() -> None:
    assert _forward_dry_run(["restart"], _flags()) == ["restart"]


@pytest.mark.parametrize("argv", [["run", "python"], ["app", "run", "python"]])
def test_dry_run_is_refused_for_run(argv, capsys) -> None:
    """Appended, --dry-run would reach the program; refuse instead."""
    with pytest.raises(SystemExit) as exc:
        _forward_dry_run(argv, _flags(dry_run=True))
    assert exc.value.code == ExitCode.USAGE_ERROR
    assert "--dry-run" in capsys.readouterr().err


# ============================================================================
# _deploy_source_path — honor explicit directory argument
# ============================================================================


def test_deploy_source_defaults_to_cwd() -> None:
    assert _deploy_source_path(["deploy", "myapp"]) == Path.cwd()


def test_deploy_source_picks_up_explicit_directory(tmp_path: Path) -> None:
    """
    ``hop3 deploy <app> <dir>`` must be packaged from <dir>, and the
    preview must report it accurately.
    """
    target = tmp_path / "checkout"
    target.mkdir()
    result = _deploy_source_path(["deploy", "myapp", str(target)])
    assert result == Path(str(target))


def test_deploy_source_skips_flag_positionals() -> None:
    """Flags interleaved with positionals should not be mistaken for a directory."""
    result = _deploy_source_path(["deploy", "myapp", "--quiet"])
    assert result == Path.cwd()


# ============================================================================
# _handle_deploy_preview --dry-run
# ============================================================================


def _targeted() -> Config:
    config = Config(data={})
    config.set_target(
        Target("dev", "https://dev.example.com", None, ContextSource.FLAG)
    )
    return config


def test_dry_run_for_deploy_prints_plan_and_exits(tmp_path: Path, capsys) -> None:
    with (
        patch("hop3_cli.main._deploy_source_path", return_value=tmp_path),
        pytest.raises(SystemExit) as exc,
    ):
        _handle_deploy_preview(
            ["deploy", "myapp"],
            _flags(dry_run=True),
            _targeted(),
            _Resolution("myapp", "$HOP3_APP"),
        )
    assert exc.value.code == ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert "About to deploy:" in captured.out
    assert "App:      myapp" in captured.out
    assert "Context:  dev (from --context)" in captured.out


def test_dry_run_for_non_deploy_does_not_short_circuit(tmp_path: Path) -> None:
    """
    ``hop3 restart --dry-run`` should NOT print a preview and exit;
    the stray-flag warning fires separately (tested above).
    """
    _handle_deploy_preview(
        ["restart", "myapp"],
        _flags(dry_run=True),
        Config(data={}),
        _Resolution("myapp", "$HOP3_APP"),
    )  # must not raise


def test_preview_no_op_when_app_unresolved() -> None:
    _handle_deploy_preview(
        ["deploy"],
        _flags(dry_run=True),
        Config(data={}),
        _Resolution(None),
    )  # must not raise


# ============================================================================
# _compute_app_resolution
# ============================================================================


def test_app_resolves_for_an_app_scoped_command(tmp_path: Path) -> None:
    flags, _ = parse_flags(["deploy", "myapp"])
    app = _compute_app_resolution(["deploy", "myapp"], flags, resolve_context(None))
    assert app is not None  # app-scoped → resolver ran (returns an AppResolution)


def test_no_app_for_a_command_that_is_not_app_scoped() -> None:
    flags, _ = parse_flags(["apps"])
    assert _compute_app_resolution(["apps"], flags, resolve_context(None)) is None


# ============================================================================
# --force flag plumbing
# ============================================================================


def test_force_flag_sets_both_force_and_skip_confirm() -> None:
    """
    --force implies skip_confirm — a --force user has clearly opted into
    "yes, take action" — but the converse is NOT true (covered above).
    """
    flags, _ = parse_flags(["deploy", "--force"])
    assert flags.force is True
    assert flags.skip_confirm is True


def test_yes_flag_sets_skip_confirm_but_not_force() -> None:
    flags, _ = parse_flags(["deploy", "-y"])
    assert flags.skip_confirm is True
    assert flags.force is False


def test_long_yes_flag_sets_skip_confirm_but_not_force() -> None:
    flags, _ = parse_flags(["deploy", "--yes"])
    assert flags.skip_confirm is True
    assert flags.force is False


def test_force_and_yes_both_set_skip_confirm() -> None:
    flags, _ = parse_flags(["deploy", "--force", "-y"])
    assert flags.force is True
    assert flags.skip_confirm is True
