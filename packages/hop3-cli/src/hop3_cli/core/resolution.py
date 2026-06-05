# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Implicit resolution for app, context and server (ADR 036 §D7, ADR 042).

Three things resolve through layered chains, each via a dedicated function:

App resolution (extended from ADR 036 §D7 by ADR 042):

    1. `--app <name>` / `-a <name>` flag (handled before resolution; if set,
       we never call here)
    2. `$HOP3_APP` env var
    3. `.hop3-app` file in CWD or any ancestor directory up to `$HOME`
    4. `[cli].app` in `hop3.toml` in CWD or any ancestor
    5. `hop3.toml [contexts.<current>].app` (ADR 042; only when a context resolves)
    6. `hop3.toml [metadata].id` in CWD or any ancestor
    7. Git remote `hop3-<resolved-context>` — parsed app portion
    8. Server-level `default_app` (the legacy ``Context.default_app`` field;
       renamed to ``Server.default_app`` post-ADR 042 Step 4)

Context resolution (ADR 042 §Resolution chains):

    1. `--context <name>` flag
    2. `$HOP3_CONTEXT` env var
    3. `.hop3-local.toml [current].context` (Step 3 — placeholder today)
    4. Git remote `hop3-<name>` where `<name>` matches a declared [contexts.<n>]
    5. Single-[contexts.*]-block-fallback (one declared context → use it)
    6. None (operations fall back to the [metadata].id-only path)

Server resolution (ADR 042 §Resolution chains):

    1. `--server <name>` flag
    2. `$HOP3_SERVER` env var
    3. The server named by the resolved context (`[contexts.<current>].server`)
    4. Git remote `hop3-<n>` host → matching server URL in global config
    5. Single-server fallback (exactly one record in the global registry)
    6. Error

Each resolver returns both the resolved value and a structured trace, so
callers can show provenance (e.g., via `--why`) or error helpfully.
"""

from __future__ import annotations

import enum
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from hop3_cli.core.hop3_toml import first_hop3_toml

if TYPE_CHECKING:
    from collections.abc import Callable

    from hop3_cli.config import Config


class _ContextServerLookup(enum.Enum):
    """Outcome of looking up [contexts.<name>].server in CWD's hop3.toml.

    Distinguishing the three failure modes lets resolve_server emit
    specific trace entries (per ADR 042 §Resolution chains — diagnostics
    matter for the `--why` story).
    """

    NO_HOP3_TOML = "no hop3.toml"
    NO_SUCH_CONTEXT = "no such context"
    NO_SERVER_FIELD = "no server field"


class AppSource(enum.Enum):
    """Which resolution-chain source produced an ``AppResolution.app``.

    Carried as a typed sibling of the free-form ``source`` string so
    downstream consumers (notably the §D14 project-mismatch guard) can
    branch on the source without grepping the human-readable text.
    The string form is for `--why` output; the kind is for code.

    Each variant maps 1:1 to a numbered source from ADR 042
    §App resolution. The CWD-rooted subset
    (``DOTFILE``/``CLI_APP``/``CONTEXT_APP``/``METADATA_ID``) is the
    set whose hit means "the project sitting at $CWD chose this app
    explicitly" — used by ``project_guard.is_cwd_rooted``.
    """

    FLAG = "flag"  # source #1: --app
    ENV = "env"  # source #2: $HOP3_APP
    DOTFILE = "dotfile"  # source #3: .hop3-app
    CLI_APP = "cli_app"  # source #4: hop3.toml [cli].app
    CONTEXT_APP = "context_app"  # source #5: hop3.toml [contexts.<n>].app
    METADATA_ID = "metadata_id"  # source #6: hop3.toml [metadata].id
    # Source #7 (git remote) intentionally absent: the caller folds the
    # parsed remote into ``cli_app=`` upstream of ``resolve_app``, so
    # those hits surface as ``FLAG``. Adding GIT_REMOTE here would lie.
    SERVER_DEFAULT = "server_default"  # source #8: server's default_app
    UNRESOLVED = "unresolved"


_CWD_ROOTED_APP_SOURCES: frozenset[AppSource] = frozenset({
    AppSource.DOTFILE,
    AppSource.CLI_APP,
    AppSource.CONTEXT_APP,
    AppSource.METADATA_ID,
})


def is_cwd_rooted(kind: AppSource) -> bool:
    """True iff the source means "the project at CWD chose this app".

    The contract used by ``project_guard.check_project_mismatch`` to
    decide whether a name mismatch is a genuine footgun (env var or
    server default points elsewhere) versus an intentional override
    that the project itself wrote (``[cli].app``, ``[contexts.x].app``,
    or a ``.hop3-app`` file inside the tree).
    """
    return kind in _CWD_ROOTED_APP_SOURCES


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

    @property
    def resolved(self) -> bool:
        return bool(self.context)


@dataclass(frozen=True)
class ServerResolution:
    """Result of resolving the target server (ADR 042)."""

    server: str | None
    source: str
    trace: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return bool(self.server)


def resolve_app(
    cli_app: str | None,
    config: Config,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    resolved_context: str | None = None,
) -> AppResolution:
    """Resolve the effective app name per ADR 036 §D7 + ADR 042 §App resolution.

    Args:
        cli_app: App passed explicitly via `--app` / `-a` (highest priority).
        config: Config object (used for server-level default_app fallback).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
        resolved_context: Name of the currently-resolved project context
            (from ``resolve_context()``). When provided and matching a
            declared ``[contexts.<name>]`` block in the nearest hop3.toml,
            its ``app`` field acts as source #5 (between ``[cli].app`` and
            ``[metadata].id``). The "load-bearing" addition from ADR 042 —
            the path that makes "same codebase, different app per environment"
            work without sticky global state.
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
    #   [cli].app                         (explicit per-project override)
    #   [contexts.<resolved_context>].app (ADR 042 — the multi-env source)
    #   [metadata].id                     (canonical project name)
    if resolved_context is None:
        # Explicit breadcrumb that source #5 was considered. Without this,
        # --why output silently jumps from #4 to #6 and an operator can't
        # tell whether the context source was tried.
        trace.append("hop3.toml [contexts.<current>].app: (no resolved context)")
    toml_resolution = _resolve_from_hop3_toml(cwd, home, trace, resolved_context)
    if toml_resolution is not None:
        return toml_resolution

    # Source 7: git-remote app portion. The caller is expected to feed
    # the parsed remote in via ``cli_app=`` when they want this source
    # active — keeping resolve_app a pure function. We still emit a
    # trace breadcrumb so the chain is visibly complete.
    trace.append("git remote app: (skipped — caller folds it in via cli_app)")

    # Source 8: server-level default_app fallback.
    #
    # Reads from `_known_server_records` so the lookup transparently
    # spans the legacy config.toml [contexts.*].default_app, any
    # config.toml [servers.*], AND the post-Step-4 servers.toml. Without
    # this, `hop3 server use --default-app foo` would write to
    # servers.toml but `config.get_default_app()` (legacy reader) would
    # return '' — source #8 silently dead.
    ctx_name = config.get_current_context_name()
    if ctx_name:
        records = _known_server_records(config)
        rec = records.get(ctx_name)
        srv_app = rec.get("default_app") if isinstance(rec, dict) else None
        if srv_app:
            trace.append(f"server {ctx_name!r} default_app: {srv_app!r}")
            return AppResolution(
                app=srv_app,
                source=f"server {ctx_name!r} default app",
                trace=tuple(trace),
                kind=AppSource.SERVER_DEFAULT,
            )
        trace.append(f"server {ctx_name!r} default_app: (not set)")
    else:
        trace.append("server: (none active)")

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
            context=cli_value, source=f"{flag_name} flag", trace=tuple(trace)
        )
    trace.append(f"flag {flag_name}: (not given)")

    env_ctx = (env.get(env_name) or "").strip()
    if env_ctx:
        trace.append(f"${env_name}: {env_ctx!r}")
        return ContextResolution(
            context=env_ctx, source=f"${env_name}", trace=tuple(trace)
        )
    trace.append(f"${env_name}: (not set)")
    return None


def _try_local_overlay(
    cwd: Path, home: Path, trace: list[str]
) -> ContextResolution | None:
    """Source #3 dispatcher: read ``.hop3-local.toml [current].context``.

    Returns a ContextResolution on hit, None on miss (caller continues to
    the git-remote/declared-context sources). Either way, appends a trace
    entry. Extracted from ``resolve_context`` to keep that function's
    branch count below the lint ceiling.
    """
    # Imported lazily so the resolver stays cheap when the file isn't there.
    from hop3_cli.core.local_overlay import read_overlay  # noqa: PLC0415

    overlay = read_overlay(cwd=cwd, home=home)
    if overlay.current_context:
        trace.append(
            f".hop3-local.toml ({overlay.path}) [current].context: "
            f"{overlay.current_context!r}"
        )
        return ContextResolution(
            context=overlay.current_context,
            source=f".hop3-local.toml at {overlay.path}",
            trace=tuple(trace),
        )
    if overlay.path is None:
        trace.append(".hop3-local.toml: (not found)")
    else:
        trace.append(f".hop3-local.toml ({overlay.path}) [current].context: (not set)")
    return None


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
    resolved_context: str | None = None,
) -> AppResolution | None:
    """Consult the nearest hop3.toml for app sources 4-6.

    Priority within hop3.toml:
    - `[cli].app` — explicit per-project CLI override (wins when set)
    - `[contexts.<resolved_context>].app` — ADR 042 source #5, the path
      that makes "same codebase, different app per environment" work
    - `[metadata].id` — canonical project name; the "I'm physically
      standing in this project" fallback

    Appends trace entries for each sub-source tried, and returns an
    AppResolution on hit or None on miss.
    """
    candidate, data = first_hop3_toml(start, stop_at)
    if candidate is None:
        trace.append("hop3.toml: (not found)")
        return None

    cli_app, ctx_app, meta_id = _extract_app_keys(data, resolved_context)
    if cli_app:
        trace.append(f"hop3.toml ({candidate}) [cli].app: {cli_app!r}")
        return AppResolution(
            app=cli_app,
            source=f"hop3.toml [cli].app at {candidate}",
            trace=tuple(trace),
            kind=AppSource.CLI_APP,
        )
    trace.append(f"hop3.toml ({candidate}) [cli].app: (not set)")
    if ctx_app:
        trace.append(
            f"hop3.toml ({candidate}) [contexts.{resolved_context}].app: {ctx_app!r}"
        )
        return AppResolution(
            app=ctx_app,
            source=(f"hop3.toml [contexts.{resolved_context}].app at {candidate}"),
            trace=tuple(trace),
            kind=AppSource.CONTEXT_APP,
        )
    if resolved_context is not None:
        trace.append(
            f"hop3.toml ({candidate}) [contexts.{resolved_context}].app: (not set)"
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


def _extract_app_keys(
    data: dict[str, Any], resolved_context: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """Extract ([cli].app, [contexts.<resolved>].app, [metadata].id) from parsed data.

    Any element of the tuple may be None. The middle element is always
    None when ``resolved_context`` is None or when the named context block
    doesn't exist.
    """
    cli = data.get("cli", {})
    cli_app = cli.get("app") if isinstance(cli, dict) else None

    ctx_app: str | None = None
    if resolved_context is not None:
        contexts = data.get("contexts", {})
        if isinstance(contexts, dict):
            ctx_block = contexts.get(resolved_context)
            if isinstance(ctx_block, dict):
                ctx_app = ctx_block.get("app")

    metadata = data.get("metadata", {})
    meta_id = metadata.get("id") if isinstance(metadata, dict) else None

    return (
        cli_app.strip() if isinstance(cli_app, str) and cli_app.strip() else None,
        ctx_app.strip() if isinstance(ctx_app, str) and ctx_app.strip() else None,
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
    git_remote_hint: str | None = None,
) -> ContextResolution:
    """Resolve the current project context per ADR 042 §Resolution chains.

    Args:
        cli_context: Context name passed via ``--context`` (highest priority).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
        git_remote_hint: When the caller has already parsed a ``hop3-<name>``
            git remote (via ``parse_hop3_git_remote``), it can pass the
            ``<name>`` portion here so the resolver consults source #4 without
            re-running git itself. Optional; resolver does not run git on its own.
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

    # Source 3: .hop3-local.toml [current].context (ADR 042 §File layout).
    # The legacy .hop3-context one-liner is retired (Step 7); users with a
    # stale .hop3-context get nothing from it and must re-run
    # ``hop3 context use <name>`` to write a fresh .hop3-local.toml.
    overlay_resolution = _try_local_overlay(cwd, home, trace)
    if overlay_resolution is not None:
        return overlay_resolution

    # Source 4: git remote `hop3-<name>` matching a declared context block.
    # The caller passes a pre-parsed hint when one is available.
    if git_remote_hint:
        declared = _declared_context_names(cwd, home)
        if git_remote_hint in declared:
            trace.append(f"git remote hop3-{git_remote_hint}: matches declared context")
            return ContextResolution(
                context=git_remote_hint,
                source=f"git remote hop3-{git_remote_hint}",
                trace=tuple(trace),
            )
        trace.append(f"git remote hop3-{git_remote_hint}: not declared in hop3.toml")
    else:
        trace.append("git remote: (no hop3-* remote)")

    # Source 5: single-[contexts.*]-block-fallback.
    declared = _declared_context_names(cwd, home)
    if len(declared) == 1:
        only = declared[0]
        trace.append(f"hop3.toml [contexts.*]: exactly one ({only!r})")
        return ContextResolution(
            context=only,
            source="single declared context (hop3.toml)",
            trace=tuple(trace),
        )
    if declared:
        trace.append(
            f"hop3.toml [contexts.*]: {len(declared)} declared ({', '.join(declared)})"
        )
    else:
        trace.append("hop3.toml [contexts.*]: (none declared)")

    # Source 6: unresolved — the [metadata].id-only path takes over.
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


# =============================================================================
# Server resolution (ADR 042)
# =============================================================================


def resolve_server(
    cli_server: str | None,
    config: Config,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    resolved_context: str | None = None,
    git_remote_hint: tuple[str, str] | None = None,
) -> ServerResolution:
    """Resolve the target server per ADR 042 §Resolution chains.

    Args:
        cli_server: Server name passed via ``--server`` (highest priority).
        config: CLI Config; the source of server records (today: the
            existing ``[contexts.*]`` blocks in ~/.config/hop3-cli/config.toml,
            renamed to ``[servers.*]`` post-Step-4).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
        resolved_context: Name of the resolved project context. When set
            and matching a declared ``[contexts.<n>]`` block in CWD's
            hop3.toml, its ``server`` field becomes source #3.
        git_remote_hint: Pre-parsed ``(host, app)`` from ``parse_hop3_git_remote``.
            When ``host`` matches a known server's URL, that server name is
            source #4.
    """
    cwd = cwd or Path.cwd()
    if env is None:
        env = dict(os.environ)
    home = home or Path.home()

    trace: list[str] = []

    # Source 1: --server flag
    if cli_server:
        trace.append(f"flag: --server {cli_server!r}")
        return ServerResolution(
            server=cli_server, source="--server flag", trace=tuple(trace)
        )
    trace.append("flag --server: (not given)")

    # Source 2: $HOP3_SERVER
    env_srv = (env.get("HOP3_SERVER") or "").strip()
    if env_srv:
        trace.append(f"$HOP3_SERVER: {env_srv!r}")
        return ServerResolution(
            server=env_srv, source="$HOP3_SERVER", trace=tuple(trace)
        )
    trace.append("$HOP3_SERVER: (not set)")

    # Source 3: resolved context's server field. Three distinct miss modes
    # get three distinct trace entries so --why diagnostics are specific.
    if resolved_context is not None:
        ctx_server = _try_context_server(cwd, home, resolved_context, trace)
        if ctx_server is not None:
            return ServerResolution(
                server=ctx_server,
                source=f"hop3.toml [contexts.{resolved_context}].server",
                trace=tuple(trace),
            )

    # Source 4: git remote host → known server name.
    if git_remote_hint is not None:
        host, _app = git_remote_hint
        matched = _server_for_host(config, host)
        if matched:
            trace.append(f"git remote host {host!r}: matches server {matched!r}")
            return ServerResolution(
                server=matched,
                source=f"git remote host {host!r}",
                trace=tuple(trace),
            )
        # Enrich the miss with the candidates we checked against — the
        # most common cause of a miss is "your server is registered under
        # a different hostname than what your git remote uses".
        candidate_names = sorted(_known_server_records(config).keys())
        candidates = ", ".join(candidate_names) if candidate_names else "(none)"
        trace.append(
            f"git remote host {host!r}: no matching server (checked: {candidates})"
        )
    else:
        trace.append("git remote: (no hop3-* remote)")

    # Source 5: single-server fallback. Reads from BOTH `servers` and
    # `contexts` table keys so this works either side of the Step-4 rename.
    server_names = sorted(_known_server_records(config).keys())
    if len(server_names) == 1:
        only = server_names[0]
        trace.append(f"global config: exactly one server ({only!r})")
        return ServerResolution(
            server=only,
            source="single declared server (global config)",
            trace=tuple(trace),
        )
    if server_names:
        trace.append(
            f"global config: {len(server_names)} servers ({', '.join(server_names)})"
        )
    else:
        trace.append("global config: (no servers)")

    # Source 6: unresolved.
    return ServerResolution(server=None, source="(unresolved)", trace=tuple(trace))


def _context_server_from_hop3_toml(
    start: Path, stop_at: Path, context_name: str
) -> tuple[str | None, _ContextServerLookup | None]:
    """Read ``[contexts.<context_name>].server`` from the nearest hop3.toml.

    Returns a ``(server_name, failure_reason)`` pair:

    - ``(server_name, None)`` on success.
    - ``(None, _ContextServerLookup.NO_HOP3_TOML)`` when no hop3.toml exists.
    - ``(None, _ContextServerLookup.NO_SUCH_CONTEXT)`` when the file exists
      but ``[contexts.<context_name>]`` is undeclared.
    - ``(None, _ContextServerLookup.NO_SERVER_FIELD)`` when the block exists
      but lacks a ``server`` field.

    Distinguishing the three lets the caller emit specific trace entries.
    """
    path, data = first_hop3_toml(start, stop_at)
    if path is None or not data:
        # ``data == {}`` happens for two distinct reasons:
        # - no hop3.toml found in the walked range (path is None)
        # - file found but unreadable / unparseable (path set, data empty)
        # Both surface as NO_HOP3_TOML — there's no usable context
        # structure to consult, and the caller's trace string ("no
        # hop3.toml in CWD or ancestors") is the more accurate one for
        # the operator either way.
        return None, _ContextServerLookup.NO_HOP3_TOML
    contexts = data.get("contexts", {})
    if not isinstance(contexts, dict):
        return None, _ContextServerLookup.NO_SUCH_CONTEXT
    block = contexts.get(context_name)
    if not isinstance(block, dict):
        return None, _ContextServerLookup.NO_SUCH_CONTEXT
    server = block.get("server")
    if isinstance(server, str) and server.strip():
        return server.strip(), None
    return None, _ContextServerLookup.NO_SERVER_FIELD


def _try_context_server(
    cwd: Path, home: Path, resolved_context: str, trace: list[str]
) -> str | None:
    """Source #3 dispatcher for resolve_server.

    Looks up ``[contexts.<resolved_context>].server`` in CWD's hop3.toml,
    appends a specific trace entry for whichever outcome occurred, and
    returns the resolved server name (or None on any miss). Extracted
    from ``resolve_server`` to keep that function's branch count below
    the lint ceiling.
    """
    ctx_server, failure = _context_server_from_hop3_toml(cwd, home, resolved_context)
    if ctx_server:
        trace.append(f"hop3.toml [contexts.{resolved_context}].server: {ctx_server!r}")
        return ctx_server
    # ``_context_server_from_hop3_toml``'s contract: on miss, ``failure`` is
    # the specific ``_ContextServerLookup`` variant; never None. The assert
    # narrows the type for pyrefly and crashes loudly if the contract drifts.
    assert failure is not None
    reason_text = {
        _ContextServerLookup.NO_HOP3_TOML: ("(no hop3.toml in CWD or ancestors)"),
        _ContextServerLookup.NO_SUCH_CONTEXT: (
            f"(no [contexts.{resolved_context}] block)"
        ),
        _ContextServerLookup.NO_SERVER_FIELD: (
            "(block exists but `server` field is missing)"
        ),
    }[failure]
    trace.append(f"hop3.toml [contexts.{resolved_context}].server: {reason_text}")
    return None


def _known_server_records(config: Config) -> dict[str, dict]:
    """Merge server records from every storage location the CLI knows about.

    Three sources, in update-order (later wins on name collision):

    1. ``config.data["contexts"]`` — legacy pre-ADR-042 location.
       Drained by Step 4's migration; remains as a fallback during the
       transition window.
    2. ``config.data["servers"]`` — same-file legacy alternative shape
       observed in some early ADR-042 drafts; kept for robustness.
    3. ``~/.config/hop3-cli/servers.toml`` — post-ADR-042 canonical
       location (Step 4). Loaded lazily on each call so a freshly-
       written record is picked up without a CLI restart.

    Step 7 retires sources 1 and 2.
    """
    merged: dict[str, dict] = {}
    for table_key in ("contexts", "servers"):
        records = config.data.get(table_key, {})
        if isinstance(records, dict):
            merged.update({n: r for n, r in records.items() if isinstance(r, dict)})

    # Source 3: the new servers.toml file. Imported lazily so resolution.py
    # doesn't depend on the registry module at import time.
    try:
        from hop3_cli.core.server_registry import load_registry  # noqa: PLC0415

        registry = load_registry()
    except (ImportError, OSError):
        return merged

    for name, rec in registry.records.items():
        merged[name] = {
            "url": rec.url,
            "api_url": rec.url,  # compat with code that still reads api_url
            "token": rec.token,
            "ssh_user": rec.ssh_user,
            "ssh_port": rec.ssh_port,
            "protected": rec.protected,
            "default_app": rec.default_app,
        }
    return merged


def _server_for_host(config: Config, host: str) -> str | None:
    """Find the server record whose URL has exactly ``host`` as its hostname.

    Uses ``urllib.parse.urlparse`` for exact hostname comparison instead of
    substring matching. Catches the prefix-collision bug where
    ``hop3.example.com`` would otherwise silently match a server URL like
    ``https://eu.hop3.example.com``.

    Comparison is case-insensitive (DNS is case-insensitive). When two
    records share a hostname, iteration order picks the first match; the
    caller is responsible for keeping URLs unique.
    """
    needle = (host or "").strip().lower()
    if not needle:
        return None
    for name, rec in _known_server_records(config).items():
        url = rec.get("api_url") or rec.get("url") or ""
        if not isinstance(url, str) or not url:
            continue
        parsed_host = _hostname_from_url(url)
        if parsed_host is not None and parsed_host == needle:
            return name
    return None


def _hostname_from_url(url: str) -> str | None:
    """Extract the lowercase hostname from a URL. None on parse failure.

    Handles both standard schemes (``https://host[:port]/path``) and
    scheme-less forms (``host:port``). Stripped + lowercased for
    comparison.
    """
    try:
        parsed = urlparse(url if "://" in url else f"//{url}", scheme="")
    except ValueError:
        return None
    host = parsed.hostname
    if host:
        return host.strip().lower()
    return None


# =============================================================================
# Git remote parsing (ADR 042 — feeds resolve_context / resolve_server / resolve_app)
# =============================================================================


_GIT_REMOTE_URL_RE = re.compile(
    r"^(?:ssh://)?(?:hop3@)?(?P<host>[^:/]+)[:/]+(?P<app>[A-Za-z0-9._-]+)$"
)


def parse_hop3_git_remote(
    cwd: Path | None = None,
    *,
    runner: Callable[[list[str], Path], str | None] | None = None,
) -> tuple[str, str, str] | None:
    """Find the first ``hop3-<env>`` git remote and parse its URL.

    Returns ``(env, host, app)`` when exactly one ``hop3-*`` remote is
    present and its URL parses; ``None`` otherwise. The CLI uses this
    return value as an input to:

    - context resolution source #4 (``env``)
    - server resolution source #4 (``host``)
    - app resolution source #7 (``app``)

    Args:
        cwd: Directory in which to invoke git (defaults to ``Path.cwd()``).
        runner: Test seam — a callable that takes (argv, cwd) and returns
            the subprocess stdout (or None on failure). Defaults to a
            ``subprocess.run`` wrapper that swallows errors.

    Returns:
        ``(env, host, app)`` tuple, or ``None`` if no parsable ``hop3-*``
        remote is found.
    """
    cwd = cwd or Path.cwd()
    runner = runner or _default_git_runner

    raw = runner(["git", "remote", "-v"], cwd)
    if not raw:
        return None

    # Lines look like: "hop3-prod\tssh://hop3@example.com:myapp (push)"
    # We want the fetch URL of the first hop3-* remote.
    candidates: dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        if not name.startswith("hop3-"):
            continue
        # Prefer the (fetch) entry over (push) when both exist.
        if name not in candidates or "(fetch)" in line:
            candidates[name] = url

    if not candidates:
        return None

    # When multiple hop3-* remotes are present, the resolver can't pick
    # one without operator intent. Surface None and let the caller
    # disambiguate via --context / --server / explicit configuration.
    if len(candidates) > 1:
        return None

    (name, url) = next(iter(candidates.items()))
    env = name.removeprefix("hop3-")
    match = _GIT_REMOTE_URL_RE.match(url)
    if not match:
        return None
    return env, match.group("host"), match.group("app")


def _default_git_runner(argv: list[str], cwd: Path) -> str | None:
    """Run a git command and return stdout. Returns None on any failure.

    Kept tiny and side-effect-free: we don't raise on missing git, on a
    non-git directory, or on remote-list failure — those all just mean
    "no git remote to use here".
    """
    import subprocess  # noqa: PLC0415

    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout
