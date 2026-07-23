# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for implicit app resolution (ADR 036 D7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from hop3_cli.commands.flags import CliFlags
from hop3_cli.core.resolution import (
    AppResolution,
    ContextResolution,
    resolve_app,
    resolve_context,
)
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import _inject_resolved_app, run_command_from_args

if TYPE_CHECKING:
    from pathlib import Path


def test_flag_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit --app always wins."""
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")

    r = resolve_app(
        cli_app="from-flag",
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.resolved
    assert r.app == "from-flag"
    assert "flag" in r.source.lower()


def test_env_var_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-env"
    assert "HOP3_APP" in r.source


def test_dotfile_beats_context_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"
    assert ".hop3-app" in r.source


def test_dotfile_search_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.hop3-app` in an ancestor directory is found."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-ancestor\n")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)

    r = resolve_app(cli_app=None, cwd=sub, home=tmp_path)
    assert r.app == "from-ancestor"


def test_dotfile_search_stops_at_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search doesn't escape above $HOME."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    # We can't easily place a .hop3-app outside tmp_path with pytest fixtures,
    # but we CAN verify the symmetric property: with nothing inside tmp_path,
    # resolution must fail rather than wander up the filesystem.
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)

    r = resolve_app(cli_app=None, cwd=sub, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_hop3_toml_cli_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-toml"
    assert "hop3.toml" in r.source


def test_dotfile_beats_hop3_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.hop3-app` has higher priority than hop3.toml."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"


def test_hop3_toml_metadata_id_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[metadata].id alone (no [cli].app) should resolve the app."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "my-project"\n')

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "my-project"
    assert "[metadata].id" in r.source


def test_metadata_id_outranks_global_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Regression: standing inside a project must beat the sticky global default.

    This is the wrong-app-deployed bug we hit in prod: `hop3 use foo`
    set a global default that followed the user into every directory,
    including ones containing other projects with their own [metadata].id.
    """
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "ac-sciences"\n')

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "ac-sciences", (
        "the project I am physically standing in must win over the "
        "global sticky default"
    )


def test_cli_app_still_beats_metadata_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[cli].app is more explicit than [metadata].id and keeps priority."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text(
        '[metadata]\nid = "default-name"\n[cli]\napp = "override-name"\n'
    )

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "override-name"


def test_metadata_id_searches_ancestors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The [metadata].id source walks up to the project root, like [cli].app."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "rooted"\n')
    sub = tmp_path / "src" / "deep" / "leaf"
    sub.mkdir(parents=True)

    r = resolve_app(cli_app=None, cwd=sub, home=tmp_path)
    assert r.app == "rooted"


def test_nothing_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_trace_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    # Trace should contain entries for each source checked, in order.
    assert r.trace
    trace = "\n".join(r.trace)
    assert "HOP3_APP" in trace
    assert ".hop3-app" in trace
    assert "hop3.toml" in trace


def test_unreadable_dotfile_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unparseable hop3.toml should not crash resolution."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text("this is not valid toml [[[ ")

    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    # The unparseable hop3.toml is ignored; nothing else resolves.
    assert not r.resolved
    assert r.app is None


def test_appresolution_dataclass_is_frozen() -> None:
    r = AppResolution(app="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        setattr(r, "app", "bar")  # ruff:ignore[set-attr-with-constant]  # frozen: assignment must raise


# ---- the resolved app is injected as `--app NAME`, never a positional ----


def test_resolved_app_injected_as_flag_not_positional() -> None:
    """
    ADR 036 D5: the app is injected as `--app NAME`, so a command's own
    positionals (e.g. `env set KEY=VALUE`) can never be mistaken for an app —
    this is the proper fix for the `env set --context prod KEY=VALUE` bug.
    """
    resolution = AppResolution(app="ac-sciences", source="context default")
    out = _inject_resolved_app(
        ["env", "set", "SENTRY_DSN=https://k@o44322.ingest.us.sentry.io/451"],
        CliFlags(app=None),
        resolution,
        MagicMock(),
    )
    assert out == [
        "env",
        "set",
        "--app",
        "ac-sciences",
        "SENTRY_DSN=https://k@o44322.ingest.us.sentry.io/451",
    ]


def test_resolved_app_injected_for_simple_command() -> None:
    resolution = AppResolution(app="ac-sciences", source="context default")
    out = _inject_resolved_app(
        ["app", "status"], CliFlags(app=None), resolution, MagicMock()
    )
    assert out == ["app", "status", "--app", "ac-sciences"]


def test_explicit_app_on_non_app_scoped_command_aborts() -> None:
    """
    L1: `cert renew --app X` must not silently drop --app (and renew ALL).

    `cert renew` is not app-scoped, so the typed --app can't be forwarded —
    refuse loudly rather than ignore it.
    """
    with pytest.raises(SystemExit) as exc:
        _inject_resolved_app(
            ["cert", "renew"], CliFlags(app="myapp"), None, MagicMock()
        )
    assert exc.value.code == ExitCode.RESOLUTION_ERROR


def test_non_app_scoped_without_explicit_app_passes_through() -> None:
    """Without a typed --app, a non-app-scoped command is left untouched."""
    out = _inject_resolved_app(["cert", "renew"], CliFlags(app=None), None, MagicMock())
    assert out == ["cert", "renew"]


# ---- create-style commands: --app names a NEW app; never substitute ambient ----


def test_catalog_install_without_app_does_not_inject_ambient() -> None:
    """
    `catalog install <id>` names a NEW app via --app. Omitting --app must NOT
    substitute the ambient app (cwd hop3.toml / $HOP3_APP / context) as that name
    — argv is forwarded verbatim so the server's own 'requires --app' error fires.
    """
    ambient = AppResolution(app="hop3-testlab", source="[metadata].id")
    out = _inject_resolved_app(
        ["catalog", "install", "ghost"], CliFlags(app=None), ambient, MagicMock()
    )
    assert out == ["catalog", "install", "ghost"]  # unchanged, no --app injected


def test_catalog_install_with_explicit_app_is_forwarded() -> None:
    """
    An EXPLICIT --app is still forwarded (re-injected after the command name),
    since parse_flags stripped it into flags.app.
    """
    resolution = AppResolution(app="mycloud", source="--app flag")
    out = _inject_resolved_app(
        ["catalog", "install", "ghost"],
        CliFlags(app="mycloud"),
        resolution,
        MagicMock(),
    )
    assert out == ["catalog", "install", "--app", "mycloud", "ghost"]


# ---- ADR 036 D14: --why is diagnostic-only (does NOT run the command) ----


def _stub_config_for_main() -> MagicMock:
    cfg = MagicMock()
    cfg.is_configured.return_value = True
    cfg.is_authenticated.return_value = True
    cfg.set_context_override = MagicMock()
    cfg.get_current_context_name.return_value = "dev"
    cfg.get_current_context.return_value = None
    cfg.get_api_url.return_value = None
    return cfg


def test_why_flag_prints_trace_and_exits_without_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    `hop3 deploy --why` must NOT trigger the deploy — diagnostic-only.

    Regression for the footgun where `--why` printed the trace and then
    continued to execute the RPC command (e.g. an actual deploy).
    """
    rpc_executed = False

    def _record_rpc_call(*_args, **_kwargs):
        nonlocal rpc_executed
        rpc_executed = True

    with (
        patch("hop3_cli.main.load_config", side_effect=_stub_config_for_main),
        patch(
            "hop3_cli.main._apply_aliases",
            side_effect=lambda args, *a, **kw: args,
        ),
        patch("hop3_cli.main._execute_rpc_command", side_effect=_record_rpc_call),
        pytest.raises(SystemExit) as exc_info,
    ):
        run_command_from_args(["deploy", "--why"])

    assert exc_info.value.code == ExitCode.SUCCESS
    assert rpc_executed is False, "`--why` must not execute the underlying command"

    # The trace is written to stderr.
    captured = capsys.readouterr()
    assert "resolution" in captured.err.lower() or captured.err


# =============================================================================
# Context resolution (ADR 042 Step 2)
# =============================================================================


def test_resolve_context_flag_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--context flag beats every other source."""
    monkeypatch.setenv("HOP3_CONTEXT", "from-env")
    (tmp_path / ".hop3-local.toml").write_text('[current]\ncontext = "from-file"\n')
    r = resolve_context(cli_context="from-flag", cwd=tmp_path, home=tmp_path)
    assert r.resolved
    assert r.context == "from-flag"
    assert "flag" in r.source.lower()


def test_resolve_context_env_beats_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOP3_CONTEXT env var beats .hop3-local.toml."""
    monkeypatch.setenv("HOP3_CONTEXT", "from-env")
    (tmp_path / ".hop3-local.toml").write_text('[current]\ncontext = "from-file"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context == "from-env"


def test_resolve_context_overlay_used_when_no_flag_or_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``.hop3-local.toml`` is the per-project context carrier (ADR 042)."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-local.toml").write_text('[current]\ncontext = "local-ctx"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context == "local-ctx"
    assert ".hop3-local.toml" in r.source


def test_resolve_context_single_block_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When exactly one [contexts.*] block exists, the resolver picks it."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / "hop3.toml").write_text('[contexts.only]\nserver = "s"\napp = "a"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context == "only"
    assert "single" in r.source.lower()


def test_resolve_context_multiple_blocks_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two declared contexts and no signal → unresolved, with trace breadcrumb."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / "hop3.toml").write_text(
        '[contexts.dev]\nserver = "s"\n[contexts.prod]\nserver = "s"\n'
    )
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert not r.resolved
    assert "dev" in "\n".join(r.trace)
    assert "prod" in "\n".join(r.trace)


def test_resolve_context_unresolved_when_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert not r.resolved


def test_context_resolution_dataclass_is_frozen() -> None:
    r = ContextResolution(context="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        setattr(r, "context", "bar")  # ruff:ignore[set-attr-with-constant]  # frozen: assignment must raise


def test_resolve_app_trace_breadcrumb_for_git_remote_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source #6 (git-remote app) always emits a trace breadcrumb."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    r = resolve_app(cli_app=None, cwd=tmp_path, home=tmp_path)
    trace = "\n".join(r.trace)
    assert "git remote app" in trace


def test_resolve_context_uses_hop3_local_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.hop3-local.toml [local].context` is consulted as source #3a."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-local.toml").write_text('[local]\ncontext = "dev"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context == "dev"
    assert ".hop3-local.toml" in r.source


def test_resolve_context_stale_legacy_dotfile_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    ADR 042 §Migration / Step 7: the legacy ``.hop3-context`` is fully
    retired — a stale file with only that one-liner returns no context
    even when nothing else is configured. Users must re-run
    ``hop3 context use <name>`` to write a fresh ``.hop3-local.toml``.
    """
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-context").write_text("legacy-ignored\n")
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context is None


def test_resolve_context_overlay_without_current_section_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlay file lacking [local].context falls through to next source."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-local.toml").write_text('[other]\nkey = "value"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    # No further source resolves; trace shows the overlay was inspected.
    assert r.context is None
    trace = "\n".join(r.trace)
    assert ".hop3-local.toml" in trace
    assert "(not set)" in trace
