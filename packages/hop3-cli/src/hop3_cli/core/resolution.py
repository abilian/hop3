# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Implicit resolution for app and context (ADR 036 §D7, ADR 042).

Two things resolve through layered chains, each via a dedicated function. The
context name resolves here; ``core.target`` turns it into a server.

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
    CWD-rooted (explicit `--context`, or this checkout's binding). An ambient
    selection (`$HOP3_CONTEXT`, `HOP3_API_URL`) still resolves the app, but marks it ``CONTEXT_APP_AMBIENT`` so the project-mismatch
    guard fires on a foreign app. (Git-remote source folded into #1 by the caller.)

Context resolution (ADR 042, rule B):

    1. `--context <name>` flag
    2. `$HOP3_CONTEXT`, or `env` when `HOP3_API_URL` / `HOP3_DEV_MODE` is set
    3. inside a project, the checkout's binding (`.hop3-local.toml` beside
       its `hop3.toml`); a project with no binding resolves to nothing, and
       every command that reaches a server refuses
    4. outside a project, the global current context (`[cli].default_context`)

Each resolver returns both the resolved value and a structured trace, so
callers can show provenance (e.g., via `--why`) or error helpfully.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hop3_cli.config import ENV_CONTEXT_NAME
from hop3_cli.core.hop3_toml import first_hop3_toml
from hop3_cli.core.local_overlay import LOCAL_OVERLAY_FILENAME, read_binding


class AppSource(enum.Enum):
    """
    Which resolution-chain source produced an ``AppResolution.app``.

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
    # chosen by a CWD-rooted signal (explicit --context, or this checkout's
    # binding) — trusted; CONTEXT_APP_AMBIENT when chosen by the environment —
    # NOT trusted, so the project-mismatch guard still fires on a foreign app.
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
    """
    True iff the source means "the project at CWD chose this app".

    The contract used by ``project_guard.check_project_mismatch`` to
    decide whether a name mismatch is a genuine footgun (env var or
    flag points elsewhere) versus an intentional override that the
    project itself wrote (``[cli].app``, ``[metadata].id``, or a
    ``.hop3-app`` file inside the tree).
    """
    return kind in _CWD_ROOTED_APP_SOURCES


class ContextSource(enum.Enum):
    """
    Which step of rule B (ADR 042) selected the context.

    Each value is the phrase the CLI prints after the context's name, so the
    line every command shows says why it goes where it goes. The selection
    also decides whether the context's ``app`` is trusted by the
    project-mismatch guard: a context named on the command line or bound in
    this checkout was chosen for this project; one taken from the environment
    may have been exported for another.
    """

    FLAG = "from --context"
    ENV = "from HOP3_CONTEXT"
    ENV_URL = "from HOP3_API_URL"
    BINDING = "bound in this checkout"
    GLOBAL = "the global context"
    UNBOUND = "this checkout is not bound"
    UNRESOLVED = "no context selected"


_CWD_ROOTED_CONTEXT_SOURCES: frozenset[ContextSource] = frozenset({
    ContextSource.FLAG,
    ContextSource.BINDING,
})


def context_selection_is_cwd_rooted(kind: ContextSource) -> bool:
    """
    True iff the context was chosen by a CWD-rooted signal (so its app is
    trustworthy and the guard should accept it).
    """
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
    """Result of resolving the context name (ADR 042, rule B)."""

    context: str | None
    source: str
    trace: tuple[str, ...] = ()
    kind: ContextSource = ContextSource.UNRESOLVED
    # The nearest hop3.toml, when the command runs inside a project.
    project: Path | None = None

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
    """
    Resolve the effective app name per ADR 042 §App resolution.

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


def _search_dotfile(
    start: Path, stop_at: Path, filename: str
) -> tuple[Path | None, str | None]:
    """
    Search upward from `start` for a dotfile, stopping at `stop_at` (inclusive).

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
    """
    Consult the nearest hop3.toml for app sources 4, 5 & 6.

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
    """
    Extract ([cli].app, [metadata].id) from parsed hop3.toml data.

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

_TRUTHY = frozenset({"true", "1", "yes"})


def resolve_context(
    cli_context: str | None,
    *,
    default_context: str | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> ContextResolution:
    """
    Choose the context NAME per rule B of ADR 042.

    Names only: whether the name is defined, and which server it names, is
    ``core.target.resolve_target``'s job.

    Args:
        cli_context: Context name passed via ``--context`` (highest priority).
        default_context: The global current context (``[cli].default_context``),
            used only outside a project.
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
    """
    cwd = cwd or Path.cwd()
    if env is None:
        env = dict(os.environ)
    home = home or Path.home()

    trace: list[str] = []
    project, _ = first_hop3_toml(cwd, home)
    name, kind = _select_from_shell(cli_context, env, trace) or _select_from_disk(
        project, default_context, trace
    )
    return ContextResolution(
        context=name,
        source=kind.value,
        trace=tuple(trace),
        kind=kind,
        project=project,
    )


def _select_from_shell(
    cli_context: str | None, env: dict[str, str], trace: list[str]
) -> tuple[str, ContextSource] | None:
    """Steps 1 and 2 of rule B: ``--context``, then the environment."""
    if cli_context:
        trace.append(f"--context: {cli_context!r}")
        return cli_context, ContextSource.FLAG
    trace.append("--context: (not given)")

    if env_ctx := (env.get("HOP3_CONTEXT") or "").strip():
        trace.append(f"$HOP3_CONTEXT: {env_ctx!r}")
        return env_ctx, ContextSource.ENV
    trace.append("$HOP3_CONTEXT: (not set)")

    if env.get("HOP3_API_URL") or env.get("HOP3_DEV_MODE", "").lower() in _TRUTHY:
        trace.append("$HOP3_API_URL / $HOP3_DEV_MODE: set")
        return ENV_CONTEXT_NAME, ContextSource.ENV_URL
    trace.append("$HOP3_API_URL / $HOP3_DEV_MODE: (not set)")
    return None


def _select_from_disk(
    project: Path | None, default_context: str | None, trace: list[str]
) -> tuple[str | None, ContextSource]:
    """Steps 3 and 4 of rule B: the checkout's binding, or the global context."""
    if project is not None:
        overlay = project.parent / LOCAL_OVERLAY_FILENAME
        if binding := read_binding(project.parent):
            trace.append(f"binding ({overlay}): {binding!r}")
            return binding, ContextSource.BINDING
        trace.append(f"binding ({overlay}): (none)")
        return None, ContextSource.UNBOUND

    if default_context:
        trace.append(f"global current context: {default_context!r}")
        return default_context, ContextSource.GLOBAL
    trace.append("global current context: (none)")
    return None, ContextSource.UNRESOLVED


def format_context_trace(resolution: ContextResolution) -> str:
    """Render a context resolution trace for ``--why``."""
    lines = ["[context]", *(f"  {entry}" for entry in resolution.trace)]
    lines.append(f"  -> {resolution.context or '(none)'} ({resolution.source})")
    return "\n".join(lines)
