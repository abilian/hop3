# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Implicit resolution for app and context (ADR 036 §D7, ADR 042).

Two things resolve through layered chains, each via a dedicated function (the
context IS the server — one noun — so there is no third "server" chain):

App resolution (extended from ADR 036 §D7 by ADR 042):

    1. `--app <name>` / `-a <name>` flag (handled before resolution; if set,
       we never call here)
    2. `$HOP3_APP` env var
    3. `.hop3-app` file in CWD or any ancestor directory up to `$HOME`
    4. `[cli].app` in `hop3.toml` in CWD or any ancestor
    5. `[contexts.<sel>].app` — the selected context's app (ADR 042 r2)
    6. `hop3.toml [metadata].id` in CWD or any ancestor

    Source 5 is *conditionally trusted*: the wrong-app footgun is held off not by
    banning a context app, but by trusting it only when the context selection was
    CWD-rooted (explicit `--context` / in-tree `.hop3-local.toml`). An ambient
    selection (`$HOP3_CONTEXT` / ancestor overlay / single-context fallback) still
    resolves the app, but marks it ``CONTEXT_APP_AMBIENT`` so the project-mismatch
    guard fires on a foreign app. (Git-remote source folded into #1 by the caller.)

Context resolution (ADR 042 §Resolution chains):

    1. `--context <name>` flag
    2. `$HOP3_CONTEXT` env var
    3. `.hop3-local.toml [local].context`
    4. Single-[contexts.*]-block-fallback (one declared context → use it)
    5. None (operations fall back to the [metadata].id-only path)

The context IS the server (one noun) — there is no separate server-resolution
chain, and git-remote-driven resolution is dropped (ADR 042 revised).

Each resolver returns both the resolved value and a structured trace, so
callers can show provenance (e.g., via `--why`) or error helpfully.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hop3_cli.core.hop3_toml import first_hop3_toml


class AppSource(enum.Enum):
    """Which resolution-chain source produced an ``AppResolution.app``.

    Carried as a typed sibling of the free-form ``source`` string so
    downstream consumers (notably the §D14 project-mismatch guard) can
    branch on the source without grepping the human-readable text.
    The string form is for `--why` output; the kind is for code.

    Each variant maps 1:1 to a numbered source from ADR 042
    §App resolution. The CWD-rooted subset
    (``DOTFILE``/``CLI_APP``/``METADATA_ID``) is the
    set whose hit means "the project sitting at $CWD chose this app
    explicitly" — used by ``project_guard.is_cwd_rooted``.
    """

    FLAG = "flag"  # source #1: --app
    ENV = "env"  # source #2: $HOP3_APP
    DOTFILE = "dotfile"  # source #3: .hop3-app
    CLI_APP = "cli_app"  # source #4: hop3.toml [cli].app
    # Source #5: the selected context's [contexts.<sel>].app (ADR 042 r2). Split
    # by the *context selection's* provenance: CONTEXT_APP when the context was
    # chosen by a CWD-rooted signal (explicit --context / in-tree
    # .hop3-local.toml) — trusted; CONTEXT_APP_AMBIENT when chosen by an ambient
    # signal ($HOP3_CONTEXT / ancestor overlay / single-context fallback) — NOT
    # trusted, so the project-mismatch guard still fires on a foreign app.
    CONTEXT_APP = "context_app"
    CONTEXT_APP_AMBIENT = "context_app_ambient"
    METADATA_ID = "metadata_id"  # source #6: hop3.toml [metadata].id
    # Git-remote source intentionally absent: the caller folds the parsed remote
    # into ``cli_app=`` upstream of ``resolve_app``, so those hits surface as
    # ``FLAG``. Adding GIT_REMOTE here would lie.
    UNRESOLVED = "unresolved"


_CWD_ROOTED_APP_SOURCES: frozenset[AppSource] = frozenset({
    AppSource.DOTFILE,
    AppSource.CLI_APP,
    AppSource.CONTEXT_APP,  # trusted: the context was selected CWD-rooted
    AppSource.METADATA_ID,
})


def is_cwd_rooted(kind: AppSource) -> bool:
    """True iff the source means "the project at CWD chose this app".

    The contract used by ``project_guard.check_project_mismatch`` to
    decide whether a name mismatch is a genuine footgun (env var or
    flag points elsewhere) versus an intentional override that the
    project itself wrote (``[cli].app``, ``[metadata].id``, or a
    ``.hop3-app`` file inside the tree).
    """
    return kind in _CWD_ROOTED_APP_SOURCES


class ContextSource(enum.Enum):
    """How the current context was selected (ADR 042 r2).

    Decides whether a context-derived app (``AppSource.CONTEXT_APP``) is trusted
    by the project-mismatch guard. A context chosen by a *CWD-rooted* signal —
    an explicit ``--context`` or a ``.hop3-local.toml`` *inside* the project tree
    — is trusted; one chosen by an *ambient* signal (``$HOP3_CONTEXT`` exported
    globally, a ``.hop3-local.toml`` inherited from an *ancestor* directory, or
    the single-context fallback) is not — preventing an exported
    ``$HOP3_CONTEXT=prod`` from silently retargeting every checkout.
    """

    FLAG = "flag"  # --context (explicit)
    ENV = "env"  # $HOP3_CONTEXT (ambient)
    OVERLAY_INTREE = "overlay_intree"  # .hop3-local.toml at/below the project root
    OVERLAY_ANCESTOR = (
        "overlay_ancestor"  # .hop3-local.toml above the project (ambient)
    )
    SINGLE_FALLBACK = "single_fallback"  # the sole declared context, auto-selected
    UNRESOLVED = "unresolved"


_CWD_ROOTED_CONTEXT_SOURCES: frozenset[ContextSource] = frozenset({
    ContextSource.FLAG,
    ContextSource.OVERLAY_INTREE,
})


def context_selection_is_cwd_rooted(kind: ContextSource) -> bool:
    """True iff the context was chosen by a CWD-rooted signal (so its app is
    trustworthy and the guard should accept it)."""
    return kind in _CWD_ROOTED_CONTEXT_SOURCES


@dataclass(frozen=True)
class AppResolution:
    """Result of resolving the current app."""

    app: str | None
    source: (
        str  # Short human-readable description ("env", "flag", "context default", ...)
    )
    # A longer trace (list of "tried source -> result") for `--why`.
    trace: tuple[str, ...] = ()
    # Typed source kind. The ``source`` string is for humans; ``kind``
    # is for code that needs to branch on provenance without parsing.
    kind: AppSource = AppSource.UNRESOLVED

    @property
    def resolved(self) -> bool:
        return bool(self.app)


@dataclass(frozen=True)
class ContextResolution:
    """Result of resolving the current project context (ADR 042)."""

    context: str | None
    source: str
    trace: tuple[str, ...] = ()
    # How the context was selected — gates whether a context-derived app is
    # trusted by the project-mismatch guard (ADR 042 r2).
    kind: ContextSource = ContextSource.UNRESOLVED

    @property
    def resolved(self) -> bool:
        return bool(self.context)


def resolve_app(
    cli_app: str | None,
    *,
    context: ContextResolution | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> AppResolution:
    """Resolve the effective app name per ADR 042 §App resolution.

    Sources 1-4 are CWD-rooted (flag / $HOP3_APP / .hop3-app / [cli].app).
    Source 5 (ADR 042 r2) is the *selected context's* ``[contexts.<sel>].app`` —
    trusted only when the context selection was CWD-rooted (see
    ``ContextSource``); otherwise it resolves but is marked
    ``CONTEXT_APP_AMBIENT`` so the project-mismatch guard still fires. Source 6
    is ``[metadata].id``.

    Args:
        cli_app: App passed explicitly via `--app` / `-a` (highest priority).
        context: The already-resolved context (name + selection provenance);
            supplies app source #5. None disables it (app stays CWD-only).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
    """
    cwd = cwd or Path.cwd()
    if env is None:
        env = dict(os.environ)
    home = home or Path.home()

    trace: list[str] = []

    # Source 1: explicit --app flag
    if cli_app:
        trace.append(f"flag: --app {cli_app!r}")
        return AppResolution(
            app=cli_app,
            source="--app flag",
            trace=tuple(trace),
            kind=AppSource.FLAG,
        )

    trace.append("flag --app: (not given)")

    # Source 2: $HOP3_APP
    env_app = (env.get("HOP3_APP") or "").strip()
    if env_app:
        trace.append(f"$HOP3_APP: {env_app!r}")
        return AppResolution(
            app=env_app,
            source="$HOP3_APP",
            trace=tuple(trace),
            kind=AppSource.ENV,
        )
    trace.append("$HOP3_APP: (not set)")

    # Source 3: .hop3-app file in CWD or any ancestor up to $HOME
    found_file, found_app = _search_dotfile(cwd, home, ".hop3-app")
    if found_app:
        trace.append(f".hop3-app ({found_file}): {found_app!r}")
        return AppResolution(
            app=found_app,
            source=f".hop3-app at {found_file}",
            trace=tuple(trace),
            kind=AppSource.DOTFILE,
        )
    trace.append(".hop3-app: (not found)")

    # Sources 4, 5 & 6: hop3.toml in CWD or any ancestor.
    # Priority within hop3.toml:
    #   [cli].app                 (explicit per-project override)
    #   [contexts.<sel>].app      (the selected context's app — ADR 042 r2)
    #   [metadata].id             (canonical project name)
    toml_resolution = _resolve_from_hop3_toml(cwd, home, trace, context)
    if toml_resolution is not None:
        return toml_resolution

    # Source 6: git-remote app portion. The caller is expected to feed the
    # parsed remote in via ``cli_app=`` when they want this source active —
    # keeping resolve_app a pure function. We still emit a trace breadcrumb so
    # the chain is visibly complete.
    trace.append("git remote app: (skipped — caller folds it in via cli_app)")

    return AppResolution(
        app=None, source="(unresolved)", trace=tuple(trace), kind=AppSource.UNRESOLVED
    )


def _try_flag_or_env(
    cli_value: str | None,
    env: dict[str, str],
    flag_name: str,
    env_name: str,
    trace: list[str],
) -> ContextResolution | None:
    """Sources #1 and #2 dispatcher for resolve_context.

    Returns a ContextResolution when the flag or env var supplies a value,
    None otherwise. Appends a trace entry whether each source hit or missed.
    Extracted to keep ``resolve_context``'s return-count below the lint
    ceiling.
    """
    if cli_value:
        trace.append(f"flag: {flag_name} {cli_value!r}")
        return ContextResolution(
            context=cli_value,
            source=f"{flag_name} flag",
            trace=tuple(trace),
            kind=ContextSource.FLAG,
        )
    trace.append(f"flag {flag_name}: (not given)")

    env_ctx = (env.get(env_name) or "").strip()
    if env_ctx:
        trace.append(f"${env_name}: {env_ctx!r}")
        return ContextResolution(
            context=env_ctx,
            source=f"${env_name}",
            trace=tuple(trace),
            kind=ContextSource.ENV,
        )
    trace.append(f"${env_name}: (not set)")
    return None


def _try_local_overlay(
    cwd: Path, home: Path, trace: list[str]
) -> ContextResolution | None:
    """Source #3 dispatcher: read ``.hop3-local.toml [local].context``.

    Returns a ContextResolution on hit, None on miss (caller continues to
    the git-remote/declared-context sources). Either way, appends a trace
    entry. Extracted from ``resolve_context`` to keep that function's
    branch count below the lint ceiling.
    """
    # Imported lazily so the resolver stays cheap when the file isn't there.
    from hop3_cli.core.local_overlay import read_overlay  # noqa: PLC0415

    overlay = read_overlay(cwd=cwd, home=home)
    if overlay.current_context:
        kind = _classify_overlay(overlay.path, cwd, home)
        trace.append(
            f".hop3-local.toml ({overlay.path}) [local].context: "
            f"{overlay.current_context!r} (selection: {kind.value})"
        )
        return ContextResolution(
            context=overlay.current_context,
            source=f".hop3-local.toml at {overlay.path}",
            trace=tuple(trace),
            kind=kind,
        )
    if overlay.path is None:
        trace.append(".hop3-local.toml: (not found)")
    else:
        trace.append(f".hop3-local.toml ({overlay.path}) [local].context: (not set)")
    return None


def _classify_overlay(
    overlay_path: Path | None, cwd: Path, home: Path
) -> ContextSource:
    """Classify a ``.hop3-local.toml`` selection as in-tree or ancestor.

    In-tree (trusted) iff the overlay sits at or below the *project root* — the
    directory of the nearest hop3.toml at/above CWD. An overlay above that root
    is an inherited *ancestor* override (ambient, untrusted); without a project
    hop3.toml there is no context-derived app at all, so we treat it as ancestor.
    """
    if overlay_path is None:
        return ContextSource.OVERLAY_ANCESTOR
    proj_path, _ = first_hop3_toml(cwd, home)
    if proj_path is None:
        return ContextSource.OVERLAY_ANCESTOR
    proj_dir = proj_path.parent.resolve()
    overlay_dir = overlay_path.parent.resolve()
    if proj_dir == overlay_dir or proj_dir in overlay_dir.parents:
        return ContextSource.OVERLAY_INTREE
    return ContextSource.OVERLAY_ANCESTOR


def _search_dotfile(
    start: Path, stop_at: Path, filename: str
) -> tuple[Path | None, str | None]:
    """Search upward from `start` for a dotfile, stopping at `stop_at` (inclusive).

    Returns (path_of_file, contents) or (None, None).
    """
    # Walk from `start` up. Include `stop_at` itself in the search.
    current = start.resolve()
    stop_at = stop_at.resolve()
    while True:
        candidate = current / filename
        if candidate.is_file():
            try:
                return candidate, candidate.read_text().strip()
            except OSError:
                return None, None
        if current in {stop_at, current.parent}:
            break
        current = current.parent
    return None, None


def _resolve_from_hop3_toml(
    start: Path,
    stop_at: Path,
    trace: list[str],
    context: ContextResolution | None = None,
) -> AppResolution | None:
    """Consult the nearest hop3.toml for app sources 4, 5 & 6.

    Priority within hop3.toml:
    - `[cli].app` — explicit per-project CLI override (wins when set)
    - `[contexts.<sel>].app` — the selected context's app (ADR 042 r2), trusted
      per the context's selection provenance
    - `[metadata].id` — canonical project name; the "I'm physically
      standing in this project" fallback

    Appends trace entries for each sub-source tried, and returns an
    AppResolution on hit or None on miss.
    """
    candidate, data = first_hop3_toml(start, stop_at)
    if candidate is None:
        trace.append("hop3.toml: (not found)")
        return None

    cli_app, meta_id = _extract_app_keys(data)
    if cli_app:
        trace.append(f"hop3.toml ({candidate}) [cli].app: {cli_app!r}")
        return AppResolution(
            app=cli_app,
            source=f"hop3.toml [cli].app at {candidate}",
            trace=tuple(trace),
            kind=AppSource.CLI_APP,
        )
    trace.append(f"hop3.toml ({candidate}) [cli].app: (not set)")

    # Source 5: the selected context's app. Trusted (CONTEXT_APP) only when the
    # context selection was CWD-rooted; otherwise CONTEXT_APP_AMBIENT, which the
    # project-mismatch guard treats as a non-CWD source (footgun protection).
    if context is not None and context.context:
        ctx_app = _extract_context_app(data, context.context)
        if ctx_app:
            cwd_rooted = context_selection_is_cwd_rooted(context.kind)
            kind = (
                AppSource.CONTEXT_APP if cwd_rooted else AppSource.CONTEXT_APP_AMBIENT
            )
            trace.append(
                f"hop3.toml ({candidate}) [contexts.{context.context}].app: "
                f"{ctx_app!r} (selection: {context.kind.value})"
            )
            return AppResolution(
                app=ctx_app,
                source=f"hop3.toml [contexts.{context.context}].app at {candidate}",
                trace=tuple(trace),
                kind=kind,
            )
        trace.append(
            f"hop3.toml ({candidate}) [contexts.{context.context}].app: (not set)"
        )

    if meta_id:
        trace.append(f"hop3.toml ({candidate}) [metadata].id: {meta_id!r}")
        return AppResolution(
            app=meta_id,
            source=f"hop3.toml [metadata].id at {candidate}",
            trace=tuple(trace),
            kind=AppSource.METADATA_ID,
        )
    trace.append(f"hop3.toml ({candidate}) [metadata].id: (not set)")
    return None


def _extract_context_app(data: dict[str, Any], name: str) -> str | None:
    """Return ``[contexts.<name>].app`` from parsed hop3.toml data, or None."""
    contexts = data.get("contexts", {})
    if isinstance(contexts, dict):
        block = contexts.get(name)
        if isinstance(block, dict):
            app = block.get("app")
            if isinstance(app, str) and app.strip():
                return app.strip()
    return None


def _extract_app_keys(
    data: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Extract ([cli].app, [metadata].id) from parsed hop3.toml data.

    Either element may be None.
    """
    cli = data.get("cli", {})
    cli_app = cli.get("app") if isinstance(cli, dict) else None

    metadata = data.get("metadata", {})
    meta_id = metadata.get("id") if isinstance(metadata, dict) else None

    return (
        cli_app.strip() if isinstance(cli_app, str) and cli_app.strip() else None,
        meta_id.strip() if isinstance(meta_id, str) and meta_id.strip() else None,
    )


def format_trace(resolution: AppResolution) -> str:
    """Render a resolution trace as a human-readable multi-line string."""
    lines = ["[resolution]"]
    for entry in resolution.trace:
        lines.append(f"  {entry}")
    if resolution.resolved:
        lines.append(f"  -> app = {resolution.app!r} (source: {resolution.source})")
    else:
        lines.append("  -> app = (unresolved)")
    return "\n".join(lines)


# =============================================================================
# Context resolution (ADR 042)
# =============================================================================


def resolve_context(
    cli_context: str | None,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> ContextResolution:
    """Resolve the current project context per ADR 042 §Resolution chains.

    Args:
        cli_context: Context name passed via ``--context`` (highest priority).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
    """
    cwd = cwd or Path.cwd()
    if env is None:
        env = dict(os.environ)
    home = home or Path.home()

    trace: list[str] = []

    # Sources 1 & 2: explicit flag / env var.
    flag_env_resolution = _try_flag_or_env(
        cli_context, env, "--context", "HOP3_CONTEXT", trace
    )
    if flag_env_resolution is not None:
        return flag_env_resolution

    # Source 3: .hop3-local.toml [local].context (ADR 042 §File layout).
    # The legacy .hop3-context one-liner is retired (Step 7); users with a
    # stale .hop3-context get nothing from it and must re-run
    # ``hop3 context use <name>`` to write a fresh .hop3-local.toml.
    overlay_resolution = _try_local_overlay(cwd, home, trace)
    if overlay_resolution is not None:
        return overlay_resolution

    # Source 4: single-[contexts.*]-block-fallback.
    declared = _declared_context_names(cwd, home)
    if len(declared) == 1:
        only = declared[0]
        trace.append(f"hop3.toml [contexts.*]: exactly one ({only!r})")
        return ContextResolution(
            context=only,
            source="single declared context (hop3.toml)",
            trace=tuple(trace),
            kind=ContextSource.SINGLE_FALLBACK,
        )
    if declared:
        trace.append(
            f"hop3.toml [contexts.*]: {len(declared)} declared ({', '.join(declared)})"
        )
    else:
        trace.append("hop3.toml [contexts.*]: (none declared)")

    # Source 5: unresolved — the [metadata].id-only path takes over.
    return ContextResolution(context=None, source="(unresolved)", trace=tuple(trace))


def _declared_context_names(start: Path, stop_at: Path) -> list[str]:
    """Return the context names declared in the nearest hop3.toml, in order.

    Walks upward like ``_resolve_from_hop3_toml``. Returns ``[]`` when no
    hop3.toml is found or no [contexts.*] block is declared.
    """
    _, data = first_hop3_toml(start, stop_at)
    contexts = data.get("contexts", {})
    if isinstance(contexts, dict):
        return [k for k, v in contexts.items() if isinstance(v, dict)]
    return []
