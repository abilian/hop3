# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the main.py wiring of ADR 042 §D14 + §Deploy preview.

Covers the integration of `_check_project_mismatch`, `_check_stray_dry_run`,
`_handle_deploy_preview`, `_deploy_source_path`, `_matches_guarded_prefix`,
plus the regression test for the 3-tuple `parse_hop3_git_remote` /
`resolve_server` shape mismatch that nearly shipped.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_cli.commands.flags import CliFlags, parse_flags
from hop3_cli.config import Config
from hop3_cli.core.resolution import AppSource
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import (
    _check_project_mismatch,
    _check_stray_dry_run,
    _compute_resolutions,
    _deploy_source_path,
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
    """Cheap stand-in for AppResolution: only needs .resolved, .app, .source, .kind.

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
    """Real-world incident: ``hop3 deploy -y`` from the wrong directory must
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
                "hop3.toml [contexts.staging].app at /tmp/x",
                kind=AppSource.CONTEXT_APP,
            ),
        )  # must not raise


# ============================================================================
# _check_stray_dry_run — warn on misuse
# ============================================================================


def test_dry_run_silent_for_deploy(capsys) -> None:
    _check_stray_dry_run(["deploy"], _flags(dry_run=True))
    captured = capsys.readouterr()
    assert captured.err == ""


def test_dry_run_warns_for_non_deploy_verb(capsys) -> None:
    _check_stray_dry_run(["restart", "myapp"], _flags(dry_run=True))
    captured = capsys.readouterr()
    assert "--dry-run" in captured.err
    assert "restart" in captured.err


def test_dry_run_warns_for_unrelated_verb(capsys) -> None:
    _check_stray_dry_run(["logs", "myapp"], _flags(dry_run=True))
    captured = capsys.readouterr()
    assert "--dry-run" in captured.err


def test_no_dry_run_no_warning(capsys) -> None:
    _check_stray_dry_run(["restart", "myapp"], _flags())
    captured = capsys.readouterr()
    assert captured.err == ""


# ============================================================================
# _deploy_source_path — honor explicit directory argument
# ============================================================================


def test_deploy_source_defaults_to_cwd() -> None:
    assert _deploy_source_path(["deploy", "myapp"]) == Path.cwd()


def test_deploy_source_picks_up_explicit_directory(tmp_path: Path) -> None:
    """``hop3 deploy <app> <dir>`` must be packaged from <dir>, and the
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


def test_dry_run_for_deploy_prints_plan_and_exits(tmp_path: Path, capsys) -> None:
    with (
        patch("hop3_cli.main._deploy_source_path", return_value=tmp_path),
        pytest.raises(SystemExit) as exc,
    ):
        _handle_deploy_preview(
            ["deploy", "myapp"],
            _flags(dry_run=True),
            Config(data={}),
            _Resolution("myapp", "$HOP3_APP"),
            None,
            None,
        )
    assert exc.value.code == ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert "About to deploy:" in captured.out
    assert "App:      myapp" in captured.out


def test_dry_run_for_non_deploy_does_not_short_circuit(tmp_path: Path) -> None:
    """``hop3 restart --dry-run`` should NOT print a preview and exit;
    the stray-flag warning fires separately (tested above).
    """
    _handle_deploy_preview(
        ["restart", "myapp"],
        _flags(dry_run=True),
        Config(data={}),
        _Resolution("myapp", "$HOP3_APP"),
        None,
        None,
    )  # must not raise


def test_preview_no_op_when_app_unresolved() -> None:
    _handle_deploy_preview(
        ["deploy"],
        _flags(dry_run=True),
        Config(data={}),
        _Resolution(None),
        None,
        None,
    )  # must not raise


# ============================================================================
# _compute_resolutions — regression for the 3-tuple BLOCKER
# ============================================================================


def test_compute_resolutions_handles_hop3_git_remote(
    tmp_path: Path, monkeypatch
) -> None:
    """REGRESSION: ``parse_hop3_git_remote`` returns ``(env, host, app)``,
    but ``resolve_server`` declares ``git_remote_hint: tuple[str, str] | None``
    and unpacks ``host, _app = git_remote_hint``. Passing the 3-tuple
    crashed with ``ValueError: too many values to unpack (expected 2, got 3)``
    on any deploy from a checkout with a ``hop3-*`` remote.

    This regression-locks the 3→2 conversion in main._compute_resolutions.
    """
    # Clear env vars so resolve_server can't short-circuit at sources 1/2/3.
    for var in ("HOP3_SERVER", "HOP3_APP"):
        monkeypatch.delenv(var, raising=False)

    # Stub parse_hop3_git_remote to return a realistic 3-tuple.
    monkeypatch.setattr(
        "hop3_cli.main.parse_hop3_git_remote",
        lambda: ("prod", "example.com", "myapp"),
    )

    config = Config(data={"contexts": {}, "current_context": None})

    # The call must not raise. If the 3-tuple is passed through unchanged,
    # this raises ``ValueError`` inside resolve_server.
    flags, _ = parse_flags(["deploy", "myapp"])
    _ctx, _srv, app = _compute_resolutions(["deploy", "myapp"], flags, config)
    # The app resolution should at least *attempt* — we don't assert its
    # value here (depends on resolver chain), but the call must complete.
    assert app is not None


# ============================================================================
# --force flag plumbing
# ============================================================================


def test_force_flag_sets_both_force_and_skip_confirm() -> None:
    """--force implies skip_confirm — a --force user has clearly opted into
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
