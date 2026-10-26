# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
App resolution source #5 + the footgun-correct guard (ADR 042 r2, step D1).

The selected context's ``[contexts.<sel>].app`` is app source #5. It is trusted
(``CONTEXT_APP``, CWD-rooted) only when the *context selection* was CWD-rooted
(explicit ``--context``, or this checkout's binding); a selection from the
environment (``$HOP3_CONTEXT``, ``HOP3_API_URL``) yields
``CONTEXT_APP_AMBIENT`` so the project-mismatch guard still fires.
"""

from __future__ import annotations

from hop3_cli.core.project_guard import check_project_mismatch
from hop3_cli.core.resolution import (
    AppSource,
    ContextResolution,
    ContextSource,
    context_selection_is_cwd_rooted,
    is_cwd_rooted,
    resolve_app,
    resolve_context,
)


def _toml(tmp, text: str):
    (tmp / "hop3.toml").write_text(text)
    return tmp


def _ctx(name: str, kind: ContextSource) -> ContextResolution:
    return ContextResolution(context=name, source="test", kind=kind)


_BASE = '[metadata]\nid="myapp"\n[contexts.prod]\napp="myapp-prod"\n'


# ---- app source #5 wiring + precedence ----


def test_context_app_resolved_and_trusted_when_cwd_rooted(tmp_path):
    _toml(tmp_path, _BASE)
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.FLAG), cwd=tmp_path, home=tmp_path
    )
    assert r.app == "myapp-prod"
    assert r.kind == AppSource.CONTEXT_APP
    assert is_cwd_rooted(r.kind) is True


def test_context_app_ambient_when_env_selected(tmp_path):
    _toml(tmp_path, _BASE)
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.ENV), cwd=tmp_path, home=tmp_path
    )
    assert r.app == "myapp-prod"
    assert r.kind == AppSource.CONTEXT_APP_AMBIENT
    assert is_cwd_rooted(r.kind) is False


def test_cli_app_wins_over_context_app(tmp_path):
    _toml(
        tmp_path,
        '[metadata]\nid="m"\n[cli]\napp="cliapp"\n[contexts.prod]\napp="ctxapp"\n',
    )
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.FLAG), cwd=tmp_path, home=tmp_path
    )
    assert r.app == "cliapp"
    assert r.kind == AppSource.CLI_APP


def test_context_app_wins_over_metadata_id(tmp_path):
    _toml(tmp_path, '[metadata]\nid="m"\n[contexts.prod]\napp="ctxapp"\n')
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.FLAG), cwd=tmp_path, home=tmp_path
    )
    assert r.app == "ctxapp"


def test_falls_through_to_metadata_when_context_has_no_app(tmp_path):
    _toml(tmp_path, '[metadata]\nid="m"\n[contexts.prod]\n')
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.FLAG), cwd=tmp_path, home=tmp_path
    )
    assert r.app == "m"
    assert r.kind == AppSource.METADATA_ID


def test_no_context_disables_source5(tmp_path):
    _toml(tmp_path, '[metadata]\nid="m"\n[contexts.prod]\napp="ctxapp"\n')
    r = resolve_app(None, context=None, cwd=tmp_path, home=tmp_path)
    assert r.app == "m"  # context not supplied -> CWD-only chain


# ---- the footgun guard ----


_FOREIGN = '[metadata]\nid="myapp"\n[contexts.prod]\napp="other-app"\n'


def test_guard_fires_on_ambient_context_foreign_app(tmp_path):
    _toml(tmp_path, _FOREIGN)
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.ENV), cwd=tmp_path, home=tmp_path
    )
    assert r.app is not None
    m = check_project_mismatch(
        r.app, r.source, r.kind, "destroy", cwd=tmp_path, home=tmp_path
    )
    assert m.is_mismatch is True


def test_guard_passes_on_cwd_rooted_context_foreign_app(tmp_path):
    _toml(tmp_path, _FOREIGN)
    r = resolve_app(
        None, context=_ctx("prod", ContextSource.FLAG), cwd=tmp_path, home=tmp_path
    )
    assert r.app is not None
    m = check_project_mismatch(
        r.app, r.source, r.kind, "destroy", cwd=tmp_path, home=tmp_path
    )
    assert m.is_mismatch is False


def test_guard_passes_on_a_bound_checkout_foreign_app(tmp_path):
    _toml(tmp_path, _FOREIGN)
    r = resolve_app(
        None,
        context=_ctx("prod", ContextSource.BINDING),
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.app is not None
    m = check_project_mismatch(
        r.app, r.source, r.kind, "destroy", cwd=tmp_path, home=tmp_path
    )
    assert m.is_mismatch is False


# ---- selection-source classification ----


def test_context_selection_cwd_rooted_classification():
    assert context_selection_is_cwd_rooted(ContextSource.FLAG)
    assert context_selection_is_cwd_rooted(ContextSource.BINDING)
    assert not context_selection_is_cwd_rooted(ContextSource.ENV)
    assert not context_selection_is_cwd_rooted(ContextSource.ENV_URL)
    assert not context_selection_is_cwd_rooted(ContextSource.GLOBAL)


def test_resolve_context_sets_kind_flag():
    assert resolve_context("prod").kind == ContextSource.FLAG


def test_resolve_context_sets_kind_env(monkeypatch):
    monkeypatch.setenv("HOP3_CONTEXT", "prod")
    assert resolve_context(None).kind == ContextSource.ENV


def test_a_single_block_is_not_a_selection(tmp_path):
    """The single-context fallback is gone: nobody chose that context."""
    _toml(tmp_path, '[metadata]\nid="m"\n[contexts.prod]\napp="m-prod"\n')
    r = resolve_context(None, cwd=tmp_path, home=tmp_path)
    assert r.context is None
    assert r.kind == ContextSource.UNBOUND


def test_resolve_context_reads_the_binding(tmp_path):
    _toml(tmp_path, '[metadata]\nid="m"\n')
    (tmp_path / ".hop3-local.toml").write_text('[local]\ncontext = "prod"\n')
    r = resolve_context(None, default_context="dev", cwd=tmp_path, home=tmp_path)
    assert (r.context, r.kind) == ("prod", ContextSource.BINDING)
