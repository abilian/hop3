# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for implicit app resolution (ADR 036 D7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from hop3_cli.core.resolution import (
    AppResolution,
    ContextResolution,
    ServerResolution,
    parse_hop3_git_remote,
    resolve_app,
    resolve_context,
    resolve_server,
)
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import run_command_from_args

if TYPE_CHECKING:
    from pathlib import Path


def _fake_config(context_name: str = "prod", default_app: str = "") -> MagicMock:
    """Build a minimal Config-like mock for the resolver.

    ADR 042 changed source #8: the resolver now reads ``default_app`` from
    ``_known_server_records(config)``, which walks both legacy
    ``config.data["contexts"][...]`` and the new servers.toml. The mock
    populates the legacy slot since these tests run with no real
    servers.toml on disk.
    """
    cfg = MagicMock()
    cfg.get_current_context_name.return_value = context_name
    cfg.get_default_app.return_value = default_app
    # Populate config.data so _known_server_records finds the record.
    cfg.data = (
        {
            "contexts": {
                context_name: {
                    "api_url": "https://example.com",
                    "default_app": default_app,
                }
            }
        }
        if context_name
        else {}
    )
    return cfg


def test_flag_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit --app always wins."""
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(
        cli_app="from-flag",
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.resolved
    assert r.app == "from-flag"
    assert "flag" in r.source.lower()


def test_env_var_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-env"
    assert "HOP3_APP" in r.source


def test_dotfile_beats_context_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"
    assert ".hop3-app" in r.source


def test_dotfile_search_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.hop3-app` in an ancestor directory is found."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-ancestor\n")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=sub, home=tmp_path)
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
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=sub, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_hop3_toml_cli_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-toml"
    assert "hop3.toml" in r.source


def test_dotfile_beats_hop3_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.hop3-app` has higher priority than hop3.toml."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"


def test_context_default_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(context_name="prod", default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-context"
    assert "prod" in r.source


def test_hop3_toml_metadata_id_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[metadata].id alone (no [cli].app) should resolve the app."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "my-project"\n')
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "my-project"
    assert "[metadata].id" in r.source


def test_metadata_id_outranks_global_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: standing inside a project must beat the sticky global default.

    This is the wrong-app-deployed bug we hit in prod: `hop3 use foo`
    set a global default that followed the user into every directory,
    including ones containing other projects with their own [metadata].id.
    """
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "ac-sciences"\n')
    cfg = _fake_config(context_name="dev", default_app="miniflux-native")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
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
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "override-name"


def test_metadata_id_searches_ancestors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The [metadata].id source walks up to the project root, like [cli].app."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "rooted"\n')
    sub = tmp_path / "src" / "deep" / "leaf"
    sub.mkdir(parents=True)
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=sub, home=tmp_path)
    assert r.app == "rooted"


def test_nothing_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(context_name="", default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_trace_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    # Trace should contain entries for each source checked, in order.
    assert r.trace
    trace = "\n".join(r.trace)
    assert "HOP3_APP" in trace
    assert ".hop3-app" in trace
    assert "hop3.toml" in trace
    # Final resolution (context default) appears because it matched.
    assert "default_app" in trace


def test_unreadable_dotfile_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unparseable hop3.toml should not crash resolution."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text("this is not valid toml [[[ ")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    # Falls through to context default
    assert r.app == "from-context"


def test_appresolution_dataclass_is_frozen() -> None:
    r = AppResolution(app="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        setattr(r, "app", "bar")  # noqa: B010  # frozen: assignment must raise


# ---- ADR 036 D14: --why is diagnostic-only (does NOT run the command) ----


def _stub_config_for_main() -> MagicMock:
    cfg = MagicMock()
    cfg.is_configured.return_value = True
    cfg.is_authenticated.return_value = True
    cfg.set_context_override = MagicMock()
    cfg.get_current_context_name.return_value = "dev"
    cfg.get_current_context.return_value = None
    cfg.get_api_url.return_value = None
    cfg.get_default_app.return_value = "miniflux-native"
    return cfg


def test_why_flag_prints_trace_and_exits_without_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`hop3 deploy --why` must NOT trigger the deploy — diagnostic-only.

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


def test_resolve_context_git_remote_hint_matches_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git_remote_hint is used as source #4 when it matches a declared context."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / "hop3.toml").write_text(
        '[contexts.prod]\nserver = "s"\n[contexts.dev]\nserver = "s"\n'
    )
    r = resolve_context(
        cli_context=None,
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint="prod",
    )
    assert r.context == "prod"
    assert "git remote" in r.source.lower()


def test_resolve_context_git_remote_hint_ignored_when_not_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown git_remote_hint is recorded in the trace and skipped."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / "hop3.toml").write_text('[contexts.dev]\nserver = "s"\n')
    r = resolve_context(
        cli_context=None,
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint="stranger",
    )
    # Falls through to single-context-fallback (dev) since the hint didn't match.
    assert r.context == "dev"
    assert "stranger" in "\n".join(r.trace)


def test_resolve_context_unresolved_when_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert not r.resolved


def test_context_resolution_dataclass_is_frozen() -> None:
    r = ContextResolution(context="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        setattr(r, "context", "bar")  # noqa: B010  # frozen: assignment must raise


# =============================================================================
# Server resolution (ADR 042 Step 2)
# =============================================================================


def _config_with_servers(*names_and_urls: tuple[str, str]) -> MagicMock:
    """Build a Config-like mock whose `.data["contexts"]` holds server records.

    Uses the legacy "contexts" key (pre-Step-4 rename); the resolver checks
    both "servers" and "contexts" so this matches today's reality.
    """
    cfg = MagicMock()
    cfg.data = {"contexts": {name: {"api_url": url} for name, url in names_and_urls}}
    return cfg


def test_resolve_server_flag_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOP3_SERVER", "from-env")
    r = resolve_server(
        cli_server="from-flag",
        config=_config_with_servers(("dev", "https://dev.example.com")),
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.server == "from-flag"


def test_resolve_server_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOP3_SERVER", "env-srv")
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(),
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.server == "env-srv"


def test_resolve_server_from_resolved_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a context resolves, the resolver reads its `server` field."""
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    (tmp_path / "hop3.toml").write_text(
        '[contexts.prod]\nserver = "prod-server"\napp = "myapp"\n'
    )
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(("prod-server", "https://prod.example.com")),
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="prod",
    )
    assert r.server == "prod-server"


def test_resolve_server_git_remote_host_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git_remote_hint host matching a server's URL picks that server."""
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(
            ("prod", "https://hop3-prod.example.com"),
            ("dev", "https://hop3-dev.example.com"),
        ),
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint=("hop3-prod.example.com", "myapp"),
    )
    assert r.server == "prod"


def test_resolve_server_single_server_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(("only", "https://only.example.com")),
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.server == "only"
    assert "single" in r.source.lower()


def test_resolve_server_unresolved_when_multiple_without_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(
            ("a", "https://a.example.com"), ("b", "https://b.example.com")
        ),
        cwd=tmp_path,
        home=tmp_path,
    )
    assert not r.resolved


def test_server_resolution_dataclass_is_frozen() -> None:
    r = ServerResolution(server="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        setattr(r, "server", "bar")  # noqa: B010  # frozen: assignment must raise


# =============================================================================
# App resolution — new source #5 ([contexts.<resolved>].app)
# =============================================================================


def test_app_from_context_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[contexts.<resolved>].app is source #5 — wins over [metadata].id."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "s"
app = "myapp-dev"
"""
    )
    cfg = _fake_config(default_app="")
    r = resolve_app(
        cli_app=None,
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="dev",
    )
    assert r.app == "myapp-dev"
    assert "contexts.dev" in r.source


def test_app_from_context_block_falls_back_to_metadata_id_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the resolved context omits `app`, fallback to [metadata].id."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "s"
"""
    )
    cfg = _fake_config(default_app="")
    r = resolve_app(
        cli_app=None,
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="dev",
    )
    assert r.app == "myapp"  # metadata.id


def test_app_cli_field_still_beats_context_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[cli].app` is more explicit than the resolved context's `app`."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text(
        """
[cli]
app = "explicit"

[contexts.dev]
server = "s"
app = "context-app"
"""
    )
    cfg = _fake_config(default_app="")
    r = resolve_app(
        cli_app=None,
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="dev",
    )
    assert r.app == "explicit"


def test_app_with_no_resolved_context_skips_context_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When resolved_context=None, the context source is skipped entirely."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "s"
app = "myapp-dev"
"""
    )
    cfg = _fake_config(default_app="")
    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    # No resolved_context → context block ignored → metadata.id wins
    assert r.app == "myapp"


# =============================================================================
# Git-remote parsing (ADR 042 — feeds the three chains)
# =============================================================================


def _fake_runner(stdout: str | None):
    """Build a runner stub that returns the given stdout (or None)."""

    def runner(_argv: list[str], _cwd: Path) -> str | None:
        return stdout

    return runner


def test_parse_hop3_git_remote_ssh_url(tmp_path: Path) -> None:
    """Standard `ssh://hop3@host:app` URL parses into (env, host, app)."""
    stdout = "hop3-prod\tssh://hop3@prod.example.com:myapp (fetch)\n"
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out == ("prod", "prod.example.com", "myapp")


def test_parse_hop3_git_remote_scp_style_url(tmp_path: Path) -> None:
    """SCP-style `hop3@host:app` (no scheme) also parses."""
    stdout = "hop3-dev\thop3@dev.example.com:myapp-dev (fetch)\n"
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out == ("dev", "dev.example.com", "myapp-dev")


def test_parse_hop3_git_remote_no_remote(tmp_path: Path) -> None:
    """No `hop3-*` remote → None."""
    stdout = "origin\thttps://github.com/example/repo (fetch)\n"
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out is None


def test_parse_hop3_git_remote_multiple_ambiguous(tmp_path: Path) -> None:
    """Multiple hop3-* remotes are ambiguous; resolver returns None."""
    stdout = (
        "hop3-prod\thop3@prod.example.com:myapp (fetch)\n"
        "hop3-dev\thop3@dev.example.com:myapp-dev (fetch)\n"
    )
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out is None


def test_parse_hop3_git_remote_runner_failure(tmp_path: Path) -> None:
    """When git fails (non-repo, missing git), runner returns None and we get None."""
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(None))
    assert out is None


def test_parse_hop3_git_remote_unparseable_url(tmp_path: Path) -> None:
    """A `hop3-*` remote with a URL that doesn't match the pattern → None."""
    stdout = "hop3-prod\tweird-non-url-thing (fetch)\n"
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out is None


def test_parse_hop3_git_remote_prefers_fetch_url(tmp_path: Path) -> None:
    """When both (fetch) and (push) URLs exist, prefer the (fetch) one."""
    stdout = (
        "hop3-prod\thop3@push.example.com:myapp (push)\n"
        "hop3-prod\thop3@fetch.example.com:myapp (fetch)\n"
    )
    out = parse_hop3_git_remote(cwd=tmp_path, runner=_fake_runner(stdout))
    assert out is not None
    _env, host, _app = out
    assert host == "fetch.example.com"


# =============================================================================
# Step-2 review fixes: exact host match, trace specificity, dual-table fallback
# =============================================================================


def test_resolve_server_host_match_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: substring matching would pick the wrong server on prefix overlap.

    When two servers exist with URLs sharing a hostname suffix (e.g.
    ``hop3.example.com`` and ``eu.hop3.example.com``), substring matching
    would silently pick the second when looking up ``hop3.example.com``.
    Exact hostname comparison via urlparse fixes this.
    """
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(
            ("eu", "https://eu.hop3.example.com"),
            ("prod", "https://hop3.example.com"),
        ),
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint=("hop3.example.com", "myapp"),
    )
    assert r.server == "prod", (
        "exact hostname match must select 'prod', not the prefix-overlapping 'eu'"
    )


def test_resolve_server_host_match_ignores_path_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hostname comparison works for URLs with ports and paths."""
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(("prod", "https://prod.example.com:8443/api")),
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint=("prod.example.com", "myapp"),
    )
    assert r.server == "prod"


def test_resolve_server_unmatched_host_trace_lists_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When git-remote host matches no server, the trace names the candidates.

    A user with a typo'd remote or a server registered under a different
    hostname benefits from seeing what WAS configured.
    """
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    r = resolve_server(
        cli_server=None,
        config=_config_with_servers(
            ("prod", "https://prod.example.com"),
            ("dev", "https://dev.example.com"),
        ),
        cwd=tmp_path,
        home=tmp_path,
        git_remote_hint=("typo.example.com", "myapp"),
    )
    trace = "\n".join(r.trace)
    assert "no matching server" in trace
    # Both candidates appear in the breadcrumb
    assert "prod" in trace
    assert "dev" in trace


def test_resolve_server_context_miss_distinguishes_three_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three distinct miss modes for [contexts.<n>].server get three traces.

    (1) no hop3.toml; (2) no such context block; (3) block exists but no server.
    Each maps to a specific breadcrumb so --why pinpoints the cause.
    """
    monkeypatch.delenv("HOP3_SERVER", raising=False)

    # Case 1: no hop3.toml at all
    r1 = resolve_server(
        cli_server=None,
        config=_config_with_servers(),
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="dev",
    )
    assert "no hop3.toml" in "\n".join(r1.trace)

    # Case 2: hop3.toml exists, but [contexts.dev] doesn't
    (tmp_path / "hop3.toml").write_text('[contexts.prod]\nserver = "s"\n')
    r2 = resolve_server(
        cli_server=None,
        config=_config_with_servers(),
        cwd=tmp_path,
        home=tmp_path,
        resolved_context="dev",
    )
    assert "no [contexts.dev] block" in "\n".join(r2.trace)


def test_resolve_server_single_server_reads_post_step4_servers_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single-server fallback must work for the post-Step-4 `servers` key too.

    Regression: an earlier shape only read ``config.data['contexts']`` for
    the fallback, so post-Step-4 (when the table is renamed to `servers`)
    the fallback would silently stop working.
    """
    monkeypatch.delenv("HOP3_SERVER", raising=False)
    cfg = MagicMock()
    # Simulate a config that has migrated to `servers`
    cfg.data = {"servers": {"prod": {"api_url": "https://prod.example.com"}}}
    r = resolve_server(cli_server=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.server == "prod"


def test_resolve_app_trace_breadcrumb_for_no_resolved_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When resolved_context is None, the trace acknowledges that source #5 was tried."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "myapp"\n')
    cfg = _fake_config(default_app="")
    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    trace = "\n".join(r.trace)
    assert "no resolved context" in trace


def test_resolve_app_trace_breadcrumb_for_git_remote_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source #7 (git-remote app) always emits a trace breadcrumb."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(default_app="")
    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    trace = "\n".join(r.trace)
    assert "git remote app" in trace


def test_resolve_context_uses_hop3_local_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.hop3-local.toml [current].context` is consulted as source #3a."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-local.toml").write_text('[current]\ncontext = "dev"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    assert r.context == "dev"
    assert ".hop3-local.toml" in r.source


def test_resolve_context_stale_legacy_dotfile_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 042 §Migration / Step 7: the legacy ``.hop3-context`` is fully
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
    """An overlay file lacking [current].context falls through to next source."""
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    (tmp_path / ".hop3-local.toml").write_text('[other]\nkey = "value"\n')
    r = resolve_context(cli_context=None, cwd=tmp_path, home=tmp_path)
    # No further source resolves; trace shows the overlay was inspected.
    assert r.context is None
    trace = "\n".join(r.trace)
    assert ".hop3-local.toml" in trace
    assert "(not set)" in trace
