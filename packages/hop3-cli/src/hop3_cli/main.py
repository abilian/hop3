# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, assert_never

if TYPE_CHECKING:
    from .commands.flags import CliFlags
    from .core.resolution import AppResolution, ContextResolution

import requests.exceptions
from jsonrpcclient import Error, Ok
from loguru import logger

from .commands import (
    confirm_destructive_action,
    get_extra_args,
    handle_help_flags,
    handle_local_command,
    is_destructive_command,
    is_local_command,
    parse_flags,
)
from .commands.arguments import describe_archive
from .config import Config, get_config
from .core.alias_registry import (
    build_registry,
    cached_subcommand_index,
    load_user_aliases_from_config,
    resolve_aliases,
)
from .core.app_scope import NEW_APP_SCOPED_COMMANDS, is_app_scoped
from .core.deploy_preview import (
    build_plan,
    domain_target_warnings,
    render_plan,
)
from .core.hop3_toml import first_hop3_toml
from .core.project_guard import check_project_mismatch
from .core.resolution import (
    format_trace,
    resolve_app,
    resolve_context,
)
from .core.workspace_guard import check_workspace_dependency
from .exceptions import AuthenticationError, CliError
from .exit_codes import ExitCode
from .rpc import Client, handle_response
from .ui import (
    RichPrinter,
    err,
    show_unauthenticated_message,
    show_unconfigured_message,
)

logger.remove()


def main() -> None:
    """Entry point for the CLI."""
    args = sys.argv[1:]
    try:
        run_command_from_args(args)
    except KeyboardInterrupt:
        # ADR 036 D16: SIGINT exits with 130 (POSIX convention: 128+SIGINT).
        # We swallow the traceback here so Ctrl-C doesn't dump a Python stack
        # at the user; the exit code lets scripts detect it.
        print(file=sys.stderr)  # newline so the next shell prompt isn't glued
        sys.exit(ExitCode.INTERRUPTED)
    except CliError as e:
        # Fallback for CliErrors not handled closer to their source (e.g. a
        # malformed config): print a clean message, not a Python traceback.
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(ExitCode.RESOLUTION_ERROR)


def run_command_from_args(cli_args: list[str]) -> None:
    """Run a CLI command from the given arguments."""
    flags, cli_args = parse_flags(cli_args)
    # Bridge --no-input into an env var so prompt-bearing helpers (which
    # don't receive flags directly) can refuse to read from a tty. See
    # hop3_cli.ui.prompts.is_no_input.
    if flags.no_input:
        import os  # ruff:ignore[import-outside-top-level]

        os.environ["HOP3_NO_INPUT"] = "1"
    printer = RichPrinter(
        verbose=flags.verbose,
        quiet=flags.quiet,
        json_output=flags.json_output,
        debug=flags.debug,
    )
    # Follow-up `hint` items echo the selectors the user actually typed, so a
    # suggested next command stays on the same context/app (a server-rendered
    # string can't carry --context — it never reaches the server).
    printer.set_suggestion_selectors(context=flags.context, app=flags.app)

    # ADR 042: one-shot migration of legacy server/context state into
    # config.toml. Runs before the config is loaded so every command — and the
    # very first invocation after an upgrade — sees the unified shape. No-op
    # (zero disk writes) on a fresh or already-migrated machine.
    _run_config_migration()

    config = load_config()

    _apply_flag_overrides(config, flags)

    if flags.verbosity >= 2:
        _print_debug_info(printer, cli_args, config, flags)

    cli_args = cli_args or ["help"]

    # ADR 036 D9: expand aliases before local/server dispatch, unless the user
    # passed --no-alias. Aliases fire on the first token only and respect the
    # collision-with-subcommand rule.
    if not flags.no_alias:
        cli_args = _apply_aliases(cli_args, config, printer, flags)

    # `tunnel` is dispatched locally (it forwards a port from THIS machine) but
    # it still connects to the configured server for the addon endpoint. The
    # main server wiring below runs *after* local dispatch, so without this an
    # explicit `--context` — or an ambient project context — would be ignored
    # and tunnel would silently hit the default server. Wire its target the same
    # way every other connecting command does (resolve-or-abort on an explicit
    # `--context`), before it dispatches.
    if cli_args[:1] == ["tunnel"] and not flags.why:
        _wire_active_server(
            cli_args, flags, config, resolve_context(cli_context=flags.context)
        )

    # Handle local commands (init, config) that don't need server
    if is_local_command(cli_args):
        if flags.verbosity >= 2:
            printer.print_debug("Handling as local command")
        if handle_local_command(cli_args, config, printer):
            return

    cli_args = handle_help_flags(cli_args)

    # ADR 042: compute resolutions once, then reuse them for app injection,
    # the project-mismatch guard, and the deploy preview. Avoids running
    # the git subprocess twice.
    context_resolution, app_resolution = _compute_resolutions(cli_args, flags, config)
    _wire_active_server(cli_args, flags, config, context_resolution)

    if flags.why:
        # Always print the resolution trace to stderr, regardless of verbosity
        # or json_output setting. `--why` is an explicit user request for
        # diagnostic output and shouldn't be gated. ``_compute_resolutions``
        # guarantees app_resolution is non-None whenever flags.why is True
        # (see its early-return condition); the assert narrows for pyrefly.
        assert app_resolution is not None
        print(format_trace(app_resolution), file=sys.stderr)
        sys.exit(ExitCode.SUCCESS)

    cli_args = _inject_resolved_app(cli_args, flags, app_resolution, printer)
    _check_project_mismatch(cli_args, flags, app_resolution)
    _check_workspace_dependency(cli_args, flags)
    _check_stray_dry_run(cli_args, flags)
    _handle_deploy_preview(cli_args, flags, config, app_resolution, context_resolution)
    _update_printer_scope(printer, config, cli_args)
    _check_prerequisites(cli_args, config, printer, flags)

    if flags.verbosity >= 2:
        printer.print_debug("Executing RPC command...")

    deploy_override = _context_deploy_override(cli_args, context_resolution)
    extra_args = _get_extra_args_safe(
        cli_args, flags.verbosity, hop3_toml_override=deploy_override
    )
    _execute_rpc_command(cli_args, config, extra_args, printer)


def _apply_flag_overrides(config: Config, flags: CliFlags) -> None:
    """
    Stash the resolution flags (--context/--app) onto the config.

    These are global flags consumed by ``parse_flags`` before the subcommand
    runs. App-scoped commands read them via the resolvers; local config-
    authoring commands read them off the config.
    """
    if flags.context:
        config.set_context_override(flags.context)
    if flags.app:
        config.set_app_override(flags.app)


def _exit_no_app_resolved(
    resolution: AppResolution, cli_args: list[str], n_consumed: int
) -> None:
    """
    Print a helpful error and exit when an app-scoped command has no app.

    Per ADR 036 D7: list the sources we tried and suggest concrete fixes.
    Exits with code 3 (resolution error per D16). Goes to stderr (D19).
    """
    cmd_display = " ".join(cli_args[:n_consumed]) or "this command"
    sources_tried = "\n  ".join(f"- {entry}" for entry in resolution.trace)
    print(
        f"Error: '{cmd_display}' requires an app, but no app could be resolved.\n"
        f"\nTried (in order):\n  {sources_tried}\n"
        f"\nTo fix, choose one:\n"
        f"  hop3 use <app>                # set sticky app for this context\n"
        f"  export HOP3_APP=<app>         # set for this shell session\n"
        f"  echo <app> > .hop3-app        # set for this directory\n"
        f"  hop3 {cmd_display} --app <app>   # one-time override",
        file=sys.stderr,
    )
    sys.exit(ExitCode.RESOLUTION_ERROR)


def _apply_aliases(
    cli_args: list[str],
    config: Config,
    printer: RichPrinter,
    flags: CliFlags,
) -> list[str]:
    """
    Expand the first-token alias (if any) per ADR 036 D9.

    Loads the effective alias registry (core + plugin + user) once per
    invocation, runs the resolver, and returns the rewritten argv. The
    subcommand-collision check is consulted via the cached command list.
    """
    user_aliases = load_user_aliases_from_config(config.config_file)
    # Warn about user/core collisions only on bare `hop3` — avoid noise on
    # every invocation. For now, we don't warn at all; `hop3 aliases` reports.
    registry = build_registry(user_aliases=user_aliases, warn_to_stderr=False)
    subcommand_index = cached_subcommand_index()
    rewritten, fired = resolve_aliases(
        cli_args, registry, known_subcommands_of_namespace=subcommand_index
    )
    if fired and flags.verbosity >= 2:
        printer.print_debug(
            f"[alias] {fired.source_token!r} -> "
            f"{' '.join(fired.expansion)!r} (source: {fired.origin})"
        )
    # When asking for help on a client-side alias, note what it expands to:
    # the alias is gone after this rewrite, and the server only sees the
    # expanded command. (Server-side aliases like `config`/`run` are noted by
    # the server's help renderer instead.)
    if fired and any(arg in {"--help", "-h"} for arg in cli_args):
        print(
            f"`{fired.source_token}` is an alias for `{' '.join(fired.expansion)}`.",
            file=sys.stderr,
        )
    return rewritten


def _context_server(name: str | None, config: Config) -> str | None:
    """
    Resolve a context NAME to its server address (ADR 042).

    ``--context`` is the one selector for every command. A name resolves
    **project-first, then global**: the nearest project ``hop3.toml
    [contexts.<name>].server``, else the user-level ``config.toml
    [contexts.<name>].server``. Returns None when ``name`` is unset or names no
    context with a server.
    """
    if not name:
        return None
    path, data = first_hop3_toml(Path.cwd(), Path.home())
    if path is not None and isinstance(data, dict):
        block = (data.get("contexts") or {}).get(name)
        if isinstance(block, dict) and isinstance(block.get("server"), str):
            if block["server"]:
                return block["server"]
    return config.get_context_server(name)


def _resolve_active_server(
    context_resolution: ContextResolution | None, config: Config
) -> str | None:
    """Server for the ambiently-selected context (.hop3-local.toml / single-context)."""
    return _context_server(getattr(context_resolution, "context", None), config)


def _wire_active_server(
    cli_args: list[str],
    flags: CliFlags,
    config: Config,
    context_resolution: ContextResolution | None,
) -> None:
    """
    Set this invocation's active server — the one connection target (ADR 042).

    ``--context <name>`` is the single selector for *every* command, app-bound or
    not (`hop3 deploy --context prod` and `hop3 apps --context prod` alike). It
    resolves project-first then global; an explicit ``--context`` MUST resolve, or
    the command aborts loud — it never silently retargets a different instance.
    With no ``--context``, the active server comes from the ambient project
    context, then the default global context, then the sole known server.
    """
    if flags.context and not flags.why:
        server = _require_context_server(flags.context, config)
        _abort_if_env_url_shadows_context(flags.context, server, config)
        config.set_active_server(server)
        return
    if active_server := _resolve_active_server(context_resolution, config):
        config.set_active_server(active_server)
        return
    if requires_authentication(cli_args) and (
        ambient := _resolve_ambient_server(config)
    ):
        config.set_active_server(ambient)


def _require_context_server(name: str, config: Config) -> str:
    """
    Resolve an explicit ``--context <name>`` to a server, or exit loud (ADR 042).

    ``--context`` is honoured for every command; it must name a context that
    resolves to a server — a project ``[contexts.<name>]`` (hop3.toml) or a global
    one (config.toml). We never silently fall back to a different server. The error
    lists what IS defined (project + global) and how to define this name.
    """
    if server := _context_server(name, config):
        return server

    path, data = first_hop3_toml(Path.cwd(), Path.home())
    known: list[str] = []
    if path is not None and isinstance(data, dict):
        project = sorted(data.get("contexts") or {})
        known.append(f"project {path}: {', '.join(project) or '(none)'}")
    glob = sorted(config.list_global_contexts())
    known.append(f"global: {', '.join(glob) or '(none)'}")
    print(
        f"Error: context {name!r} is not defined.\n"
        f"  Known contexts — {'; '.join(known)}\n"
        f"  Define it with:            hop3 context add {name} --server <addr>\n"
        f"  or while authenticating:   hop3 login --context {name} --ssh <target>",
        file=sys.stderr,
    )
    sys.exit(ExitCode.RESOLUTION_ERROR)


def _env_override_url(config: Config) -> str | None:
    """
    The connection URL ``get_api_url()`` takes from the environment, ahead of
    any resolved context — ``HOP3_DEV_MODE``'s localhost, then ``HOP3_API_URL``.
    None when no env override is in play.
    """
    import os  # ruff:ignore[import-outside-top-level]

    if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
        return config.get("api_url", "http://localhost:8000")
    return os.environ.get("HOP3_API_URL")


def _abort_if_env_url_shadows_context(
    name: str, context_server: str, config: Config
) -> None:
    """
    An explicit ``--context`` must not be silently overridden by an ambient
    ``HOP3_API_URL`` / ``HOP3_DEV_MODE`` (which ``get_api_url`` consults first).
    Connecting to the env URL while the operator asked for ``name`` would ignore
    their explicit selection and target a different server — abort loud rather
    than retarget invisibly (audit 2026-06 C1).
    """
    env_url = _env_override_url(config)
    if not env_url:
        return

    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

    if credential_store.canonicalize(env_url) == credential_store.canonicalize(
        context_server
    ):
        return

    print(
        f"Error: --context {name!r} targets {context_server}, but "
        f"HOP3_API_URL / HOP3_DEV_MODE overrides the connection to {env_url}.\n"
        f"  Connecting there would silently ignore your explicit --context.\n"
        f"  Unset the env override, or drop --context to use the env URL.",
        file=sys.stderr,
    )
    sys.exit(ExitCode.RESOLUTION_ERROR)


def _effective_default_context(config: Config) -> str | None:
    """
    The default context name iff it's what selected the active server.

    Shown in the deploy preview when no context was explicitly resolved, so the
    operator sees which context (not just which server) the deploy targets.
    Returns None when the active server came from elsewhere (HOP3_API_URL, the
    legacy default_server, or a sole known server), so the preview never names a
    context that isn't actually in play.
    """
    default = config.get_default_context()
    if default and _context_server(default, config) == config.get_api_url():
        return default
    return None


def _resolve_ambient_server(config: Config) -> str | None:
    """
    Server for a project-less command with no ``--context`` (ADR 042).

    Chain: the **default context** (`[cli].default_context` → its server) → the
    legacy unnamed default-server → the *sole* entry in the credential store →
    None. None means "ambiguous or empty" — the prerequisite check then reports it
    (server-aware via ``known_servers``).
    """
    if server := _context_server(config.get_default_context(), config):
        return server
    if default := config.get_default_server():
        return default
    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

    known = credential_store.known_servers()
    return known[0] if len(known) == 1 else None


def _compute_resolutions(
    cli_args: list[str], flags: CliFlags, config: Config
) -> tuple[ContextResolution | None, AppResolution | None]:
    """
    Run the context+app resolvers (or no-op when not needed).

    Returns ``(context_resolution, app_resolution)``. Both may be None when the
    command is not app-scoped and ``--why`` wasn't requested — the resolvers do
    real work (file reads) and must not fire for ``hop3 version``/``hop3 help``.

    ADR 042: the context IS the server (one noun), so there is no separate
    server resolution; the app resolves CWD-only.
    """
    scoped, _ = is_app_scoped(cli_args)
    if scoped or flags.why:
        context_resolution = resolve_context(cli_context=flags.context)
        # ADR 042 r2: the resolved context supplies app source #5
        # ([contexts.<sel>].app), trusted per the context's selection provenance.
        app_resolution = resolve_app(cli_app=flags.app, context=context_resolution)
        return context_resolution, app_resolution

    # Non-app-scoped commands (apps, addon list, backup list, …) still target a
    # server, so they must honor $HOP3_CONTEXT / the .hop3-local.toml pin / a
    # sole project context — not silently fall through to the global default
    # (audit 2026-06 C2). Resolve the context for them too, but only when the
    # command actually connects, so `version`/`help` still read no files.
    if requires_authentication(cli_args):
        return resolve_context(cli_context=flags.context), None
    return None, None


def _inject_resolved_app(
    cli_args: list[str],
    flags: CliFlags,
    resolution: AppResolution | None,
    printer: RichPrinter,
) -> list[str]:
    """
    Inject the resolved app as the first positional for app-scoped commands.

    The server's dispatcher and command handlers continue to expect the
    app as first positional. If no app can be resolved for an app-scoped
    command that was invoked without an explicit positional, exit with a
    structured "no app resolved" error (ADR 036 D10).
    """
    scoped, n_consumed = is_app_scoped(cli_args)
    if not scoped:
        # `parse_flags` stripped any typed `--app`/`-a` into flags.app. For an
        # app-scoped command it's re-injected below; for a command that ISN'T
        # app-scoped there's nowhere to forward it, so dropping it silently would
        # act on the wrong scope — e.g. `cert renew --app X` silently renewed ALL
        # certs (audit 2026-06 L1). Refuse loudly instead.
        if flags.app:
            cmd = " ".join(t for t in cli_args[:2] if not t.startswith("-")) or "this"
            print(
                f"Error: `hop3 {cmd}` does not take --app; the flag would be "
                f"silently ignored.\n"
                f"  Re-run without --app, or use a command that targets one app.",
                file=sys.stderr,
            )
            sys.exit(ExitCode.RESOLUTION_ERROR)
        return cli_args
    if resolution is None:
        return cli_args

    # Create-style commands (e.g. `catalog install`) name a NEW app via --app, so
    # an AMBIENT app must never be substituted as that name. When --app is omitted
    # (flags.app is falsy), forward argv unchanged so the server's own "requires
    # --app" guard fires loudly — rather than silently installing under whatever
    # app the current directory / $HOP3_APP / context resolves to.
    if not flags.app and tuple(cli_args[:n_consumed]) in NEW_APP_SCOPED_COMMANDS:
        return cli_args

    # The app is ALWAYS a flag, never a positional (ADR 036 D5). `parse_flags`
    # already stripped any user `--app`/`-a` into `flags.app`, and `resolution`
    # folds that in at top priority — so there is no positional fallback: if
    # nothing resolved, fail with the structured "no app resolved" error.
    if not resolution.resolved:
        _exit_no_app_resolved(resolution, cli_args, n_consumed)

    resolved_app = resolution.app
    assert resolved_app is not None
    # Re-introduce the resolved app as `--app NAME` right after the command
    # name. The server receives it as a flag, so a command's own positionals
    # (e.g. `env set KEY=VALUE`, the command for `run <cmd>`) can never be
    # mistaken for an app name.
    injected = [
        *cli_args[:n_consumed],
        "--app",
        resolved_app,
        *cli_args[n_consumed:],
    ]
    if flags.verbosity >= 2:
        printer.print_debug(
            f"[app resolution] injected --app {resolved_app!r} "
            f"(source: {resolution.source})"
        )
    return injected


# ADR 042 §D14: verbs that trigger the project-mismatch guard. These are
# the ones that mutate server state in a way the operator would regret
# pointing at the wrong app. Bare ``destroy`` is intentionally absent:
# alias expansion rewrites it to ``app destroy`` upstream, and the bare
# form is not in APP_SCOPED_COMMANDS — so _compute_resolutions returns
# (None, None, None) and the guard never sees it.
#
# Compare with commands/destructive.py::DESTRUCTIVE_COMMANDS, which
# carries a *different* list (verbs that require typed-name confirmation
# for destruction). The two lists overlap on ``app destroy`` but are
# semantically distinct: this list is "verbs that need to know they're
# pointing at the right app", that list is "verbs that need a typed
# acknowledgment of the resource name".
_MISMATCH_GUARDED_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("deploy",),
    ("restart",),
    ("env", "set"),
    ("config", "set"),  # back-compat alias for `env set`
    ("app", "destroy"),
)


def _matches_guarded_prefix(cli_args: list[str]) -> tuple[str, ...] | None:
    """Return the matching guarded-verb tuple, if any."""
    for prefix in _MISMATCH_GUARDED_PREFIXES:
        if len(cli_args) >= len(prefix) and tuple(cli_args[: len(prefix)]) == prefix:
            return prefix
    return None


def _check_project_mismatch(
    cli_args: list[str], flags: CliFlags, app_resolution: AppResolution | None
) -> None:
    """
    ADR 042 §D14: refuse a guarded verb when CWD's project disagrees with
    the resolved app and the operator did NOT opt in with ``--force``.

    ``-y`` / ``--yes`` alone (skip-confirmation) is NOT enough to bypass —
    the ADR explicitly separates the two intents because routine CI/scripting
    use of ``-y`` is precisely the surface this guard exists to protect.
    """
    if app_resolution is None or not app_resolution.resolved:
        return
    if _matches_guarded_prefix(cli_args) is None:
        return
    if flags.force:
        return

    verb = " ".join(_matches_guarded_prefix(cli_args) or ())
    mismatch = check_project_mismatch(
        resolved_app=app_resolution.app or "",
        resolved_source=app_resolution.source or "",
        resolved_kind=app_resolution.kind,
        verb=verb,
    )
    if mismatch.is_mismatch:
        print(mismatch.message, file=sys.stderr)
        # RESOLUTION_ERROR (3) — refusal because of inconsistent state,
        # NOT confirmation-declined (a UX event from a prompt that never
        # ran). Scripts can match on 3 to distinguish "wrong project"
        # from "user said no".
        sys.exit(ExitCode.RESOLUTION_ERROR)


def _check_workspace_dependency(cli_args: list[str], flags: CliFlags) -> None:
    """
    Refuse to deploy a uv-workspace member in isolation when it depends on a
    sibling workspace package (which would silently install from PyPI instead of
    the local source). See ``core.workspace_guard``. ``--force`` overrides.
    """
    if cli_args[:1] != ["deploy"] or flags.force:
        return

    issue = check_workspace_dependency(_deploy_source_path(cli_args))
    if issue.is_problem:
        print(issue.message, file=sys.stderr)
        sys.exit(ExitCode.RESOLUTION_ERROR)


def _check_stray_dry_run(cli_args: list[str], flags: CliFlags) -> None:
    """
    Warn (don't silently ignore) when ``--dry-run`` is given for a
    command that doesn't yet support it. Avoids the worst-of-both-worlds
    case where ``hop3 restart --dry-run`` parses the flag, takes no
    notice of it, and actually restarts.
    """
    if not flags.dry_run:
        return
    if not cli_args or cli_args[0] == "deploy":
        return
    print(
        f"warning: --dry-run is currently only honored for `hop3 deploy`; "
        f"continuing with `hop3 {cli_args[0]}` as if it were absent.",
        file=sys.stderr,
    )


def _deploy_source_path(cli_args: list[str]) -> Path:
    """
    Mirror commands.arguments._parse_deploy_args's directory-positional logic.

    ``hop3 deploy [<app>] [<dir>]`` — if the trailing positional looks like a
    directory argument, use it; otherwise CWD. This makes the preview accurate
    about what's being packaged (``hop3 deploy --dry-run /tmp/checkout`` reads
    /tmp/checkout/hop3.toml, not the operator's terminal CWD).
    """
    # cli_args at this point is post-injection: ["deploy", <app>, <maybe-dir>].
    # We treat any non-flag positional after position 2 (deploy + app) as a
    # directory argument. Same heuristic as _parse_deploy_args (last positional).
    candidates = [a for a in cli_args[1:] if not a.startswith("-")]
    if len(candidates) >= 2:
        return Path(candidates[-1])
    return Path.cwd()


def _handle_deploy_preview(
    cli_args: list[str],
    flags: CliFlags,
    config: Config,
    app_resolution: AppResolution | None,
    context_resolution: ContextResolution | None,
) -> None:
    """
    ADR 042 §Deploy preview: ``hop3 deploy`` prints a plan and exits when
    ``--dry-run`` is set. The interactive preview-and-confirm flow on plain
    ``hop3 deploy`` is gated on a TTY and bypassed by ``-y`` / ``--yes`` /
    ``--force`` / ``--no-input``.

    Also runs the DNS host-check: if an app domain doesn't resolve to the
    deploy-target server, requests will land elsewhere and 502 while the app
    looks healthy. That warning is emitted unconditionally (even under -y /
    --quiet) — it's precisely the silent failure the preview exists to prevent.
    """
    if cli_args[:1] != ["deploy"]:
        return
    if app_resolution is None or not app_resolution.resolved:
        return

    context_name = context_resolution.context if context_resolution else None
    source_path = _deploy_source_path(cli_args)
    plan = build_plan(
        source_path=source_path,
        context=context_name,
        app=app_resolution.app or "",
        server=config.get_api_url(),
        default_context=None if context_name else _effective_default_context(config),
    )
    domain_warnings = domain_target_warnings(plan.domains, config.get_api_url())

    def emit_domain_warnings() -> None:
        for w in domain_warnings:
            print(f"  warning: {w}", file=sys.stderr)

    if flags.dry_run:
        # --dry-run: print plan to stdout (so it's pipeable for review),
        # warnings to stderr (so a script that redirects stdout still
        # surfaces the dirty-tree marker), exit 0. Also show the resolved
        # archive manifest so the user can see exactly what would be uploaded
        # (and what to add to [build].ignore) without guessing.
        print(render_plan(plan))
        print("\n" + describe_archive(source_path))
        emit_domain_warnings()
        sys.exit(ExitCode.SUCCESS)

    # Default deploy: interactive preview-and-confirm. Bypassed when the
    # operator already opted out of prompts (-y / --yes / --force) or
    # disabled prompting altogether (--no-input). The plan still prints
    # in those cases — quietly — so the action surfaces in CI logs.
    if flags.skip_confirm or flags.no_input:
        if not flags.quiet:
            print(render_plan(plan), file=sys.stderr)
        emit_domain_warnings()  # always — a wrong-target deploy must surface
        return

    if not sys.stdin.isatty():
        # No tty and no --yes: refuse to deploy blind. Matches the
        # destructive-prompt non-tty behavior elsewhere.
        print(render_plan(plan), file=sys.stderr)
        emit_domain_warnings()
        print(
            "\nRefusing to deploy without a tty. Re-run with --yes (skip "
            "this prompt) or --dry-run (print the plan and exit).",
            file=sys.stderr,
        )
        sys.exit(ExitCode.CONFIRMATION_DECLINED)

    print(render_plan(plan), file=sys.stderr)
    emit_domain_warnings()
    response = input("\nDeploy? [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        print("Deploy aborted.", file=sys.stderr)
        sys.exit(ExitCode.CONFIRMATION_DECLINED)


def _update_printer_scope(
    printer: RichPrinter, config: Config, cli_args: list[str]
) -> None:
    """
    Populate printer scope so summary lines carry a [context / app] prefix.

    We best-effort-extract the app from the argv after app resolution has
    run (it's injected as `--app NAME` for app-scoped commands, ADR 036 D5).
    For non-app-scoped commands we leave app as None and the prefix falls
    back to just [context] (or nothing if no context is active).
    """
    context_name = config.get_current_context_name()
    app_name: str | None = None
    scoped, n_consumed = is_app_scoped(cli_args)
    if scoped:
        rest = cli_args[n_consumed:]
        for i, tok in enumerate(rest):
            if tok in {"--app", "-a"} and i + 1 < len(rest):
                app_name = rest[i + 1]
                break
            if tok.startswith("--app="):
                app_name = tok[len("--app=") :]
                break
    printer.set_scope(context=context_name, app=app_name)


def _print_debug_info(
    printer: RichPrinter, cli_args: list[str], config: Config, flags: CliFlags
) -> None:
    """Print debug information about the current command."""
    printer.print_debug(f"Command: {' '.join(cli_args) if cli_args else '(none)'}")
    printer.print_debug(f"Verbosity: {flags.verbosity}")

    context_name = config.get_current_context_name()
    if context_name:
        printer.print_debug(f"Context: {context_name}")

    api_url = config.get_api_url() or "(not configured)"
    printer.print_debug(f"API URL: {api_url}")


def _context_deploy_override(
    cli_args: list[str], context_resolution: ContextResolution | None
) -> bytes | None:
    """
    Context-flattened hop3.toml bytes for a `hop3 deploy` upload (ADR 042 r2 §E1).

    Strips every ``[contexts.*]`` (never uploaded) and merges the selected
    context's env/domains into the top level, so the server deploys the effective
    config — matching the deploy preview. Returns None when the command is not a
    deploy, the source has no hop3.toml, or there is nothing to flatten.
    """
    if not cli_args or cli_args[0] != "deploy":
        return None
    source_path = _deploy_source_path(cli_args)
    own = source_path / "hop3.toml"
    if not own.is_file():
        return None

    import toml  # ruff:ignore[import-outside-top-level]

    from hop3_cli.core.deploy_preview import (  # ruff:ignore[import-outside-top-level]
        flatten_for_context,
    )
    from hop3_cli.core.hop3_toml import (  # ruff:ignore[import-outside-top-level]
        read_hop3_toml,
    )

    raw = read_hop3_toml(own)
    ctx = getattr(context_resolution, "context", None)
    if "contexts" not in raw and not ctx:
        return None  # nothing to merge or strip — upload the file as-is
    effective = flatten_for_context(raw, ctx)
    return toml.dumps(effective).encode("utf-8")


def _get_extra_args_safe(
    cli_args: list[str], verbosity: int, hop3_toml_override: bytes | None = None
) -> dict:
    """Get extra args with error handling."""
    try:
        return get_extra_args(
            cli_args, verbosity=verbosity, hop3_toml_override=hop3_toml_override
        )
    except FileNotFoundError as e:
        err(f"File or directory not found: {e}")
        sys.exit(ExitCode.RESOLUTION_ERROR)
    except ValueError as e:
        # ValueError from get_extra_args means the user passed something the
        # CLI couldn't parse (bad --input flag, missing password file, etc.).
        err(f"Invalid input: {e}")
        sys.exit(ExitCode.USAGE_ERROR)
    except PermissionError as e:
        err(f"Permission denied: {e}")
        sys.exit(ExitCode.AUTHZ_ERROR)


def _check_prerequisites(
    cli_args: list[str], config: Config, printer: RichPrinter, flags: CliFlags
) -> None:
    """Check all prerequisites before executing a command."""
    # Skip all checks for commands that don't require authentication
    if not requires_authentication(cli_args):
        return

    # Check if CLI is configured
    if not config.is_configured():
        show_unconfigured_message(cli_args)
        sys.exit(ExitCode.AUTH_ERROR)

    # Check authentication - try auto-auth via SSH if not authenticated
    if not config.is_authenticated():
        try:
            _try_auto_authenticate(config, printer)
        except AuthenticationError:
            show_unauthenticated_message()
            sys.exit(ExitCode.AUTH_ERROR)

    # For destructive commands, verify token is valid BEFORE asking for confirmation
    if is_destructive_command(cli_args):
        try:
            verify_authentication(config)
        except AuthenticationError:
            # Token might be expired - try auto-auth via SSH
            try:
                _try_auto_authenticate(config, printer)
            except AuthenticationError:
                show_unauthenticated_message()
                sys.exit(ExitCode.AUTH_ERROR)

    # Prompt for confirmation on destructive commands. `--yes`/`-y`/`--force`
    # bypass entirely; `--confirm=<name>` and `--no-input` flow through.
    if not flags.skip_confirm and is_destructive_command(cli_args):
        if not confirm_destructive_action(cli_args, printer, config, flags=flags):
            # ADR 036 D16: declined confirmation (or non-tty without --yes/--confirm)
            # has its own exit code so scripts can distinguish "user said no" from
            # other failures.
            sys.exit(ExitCode.CONFIRMATION_DECLINED)


def _try_auto_authenticate(config: Config, printer: RichPrinter) -> None:
    """
    Try to authenticate automatically via SSH if available.

    Raises:
        AuthenticationError: If auto-auth is not available or fails.
    """
    from urllib.parse import urlparse  # ruff:ignore[import-outside-top-level]

    from hop3_cli.commands.local.ssh_ops import (  # ruff:ignore[import-outside-top-level]
        BootstrapError,
        get_ssh_token,
    )

    api_url = config.get_api_url()
    if not api_url:
        msg = "No API URL configured"
        raise AuthenticationError(msg)

    parsed = urlparse(api_url)
    if parsed.scheme not in {"ssh", "ssh+http"}:
        msg = f"Auto-auth requires SSH URL (got {parsed.scheme}://)"
        raise AuthenticationError(msg)

    # We have SSH access - try auto-auth
    ssh_user = parsed.username or config.get("ssh_user", "root")
    ssh_host = parsed.hostname
    ssh_target = f"{ssh_user}@{ssh_host}"

    if printer.verbosity >= 1:
        printer.print_debug(f"Auto-authenticating via SSH to {ssh_target}...")

    try:
        token = get_ssh_token(ssh_target)
    except BootstrapError as e:
        if printer.verbosity >= 1:
            printer.print_debug(f"Auto-auth failed: {e}")
        msg = f"SSH authentication to {ssh_target} failed: {e}"
        raise AuthenticationError(msg) from e

    config.update_context_token(token)
    if printer.verbosity >= 1:
        printer.print_debug("Auto-authentication successful")


def requires_authentication(cli_args: list[str]) -> bool:
    """
    Check if the command requires authentication.

    Note: Most no-auth commands (version, auth) are now handled locally
    and won't reach this check. This remains as a safety net for RPC commands.

    See also: is_help_command() in commands/help.py which checks if help output
    should be augmented with local commands (different purpose).
    """
    if not cli_args:
        return False

    # Commands that can run without authentication. Space-separated tuples per
    # ADR 036 D1.
    #
    # Matching rules:
    # - ("help",), ("version",): match as a prefix (help or any subcommand of help).
    # - ("auth", "get-token"), ("auth", "register"): match as a prefix (positional args OK).
    # - ("auth",): exact match only — bare `hop3 auth` shows help without auth,
    #   but `hop3 auth whoami` requires auth. (`auth login` / `auth logout` are
    #   handled locally and never reach this RPC-auth gate.)
    prefix_no_auth: set[tuple[str, ...]] = {
        ("help",),
        ("version",),
        ("auth", "get-token"),
        ("auth", "register"),
    }
    exact_no_auth: set[tuple[str, ...]] = {
        ("auth",),
    }

    full = tuple(cli_args)
    if full in exact_no_auth:
        return False
    for n in range(min(len(cli_args), 3), 0, -1):
        if tuple(cli_args[:n]) in prefix_no_auth:
            return False
    return True


def _execute_rpc_command(
    cli_args: list[str],
    config: Config,
    extra_args: dict,
    printer: RichPrinter,
) -> None:
    """
    Execute RPC command, handle response, and manage connection lifecycle.

    The response handling is done inside the Client context to keep SSH tunnels
    alive for streaming responses.
    """
    with Client(config=config) as client:
        # Debug: show connection info
        if printer.verbosity >= 2:
            if client.using_ssh_tunnel:
                printer.print_debug(f"Using SSH tunnel to {config.get_api_url()}")
                printer.print_debug(f"RPC endpoint: {client.rpc_url}")
            else:
                printer.print_debug(f"Direct connection to {client.rpc_url}")

        try:
            validated_extra_args: dict[str, Any] = {
                k: v
                for k, v in extra_args.items()
                if isinstance(k, str) and v is not None
            }
            response = client.rpc("cli", cli_args, **validated_extra_args)

            # Get tunnel port if using SSH tunnel (for streaming support)
            tunnel_port = None
            if client.tunnel:
                tunnel_port = client.tunnel.local_bind_port

            # Handle response INSIDE the context to keep tunnel alive for streaming
            handle_response(
                response, cli_args, config, printer, tunnel_port=tunnel_port
            )

        except requests.exceptions.SSLError:
            _handle_ssl_error(client.rpc_url)
        except requests.exceptions.ConnectionError as e:
            _handle_connection_error(e, client.rpc_url)
        except requests.exceptions.HTTPError as e:
            err(f"HTTP error while connecting to the Hop3 server:\n{e}")
            sys.exit(ExitCode.NETWORK_ERROR)
        except TimeoutError:
            err("Connection to the Hop3 server timed out.")
            sys.exit(ExitCode.NETWORK_ERROR)
        except Exception as e:
            err(f"Error while executing command:\n{e}")
            sys.exit(ExitCode.GENERAL_ERROR)


def _handle_ssl_error(rpc_url: str) -> None:
    """Handle SSL certificate verification errors."""
    err(
        f"SSL certificate verification failed for {rpc_url}.\n\n"
        "Options:\n"
        "  1. Trust this server's certificate:\n"
        "     hop3 settings set ssl_cert /path/to/server.crt\n\n"
        "  2. Disable SSL verification (less secure):\n"
        "     hop3 settings set verify_ssl false"
    )
    sys.exit(ExitCode.NETWORK_ERROR)


def _handle_connection_error(e: Exception, rpc_url: str) -> None:
    """Handle connection errors, including wrapped SSL errors."""
    error_str = str(e).lower()
    if "ssl" in error_str or "certificate" in error_str:
        _handle_ssl_error(rpc_url)
    else:
        err(f"Could not connect to the Hop3 server at {rpc_url}.\nIs it running?")
        sys.exit(ExitCode.NETWORK_ERROR)


def load_config() -> Config:
    """Load configuration from the standard user location."""
    return get_config()


def _run_config_migration() -> None:
    """
    Run the one-shot ADR-042 config migration before anything reads config.

    No-op once migrated. Aborts loudly (exit 1, nothing changed) on malformed
    input; prints a one-line summary per migration to stderr otherwise.
    """
    from hop3_cli.core.config_migration import (  # ruff:ignore[import-outside-top-level]
        MigrationError,
        migrate_legacy_config_042,
    )
    from hop3_cli.core.config_migration_v2 import (  # ruff:ignore[import-outside-top-level]
        MigrationError as MigrationErrorV2,
        migrate_config_to_token_store,
    )
    from hop3_cli.core.paths import config_dir  # ruff:ignore[import-outside-top-level]

    cfg_dir = config_dir()
    try:
        # Stage 1 (ADR 042 r1): consolidate every legacy shape into
        # config.toml [contexts.*]. Stage 2 (r2): drain those tokens into the
        # per-server store and leave config.toml secret-free. Sequential.
        notes = migrate_legacy_config_042(cfg_dir)
        notes += migrate_config_to_token_store(cfg_dir)
    except (MigrationError, MigrationErrorV2) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(ExitCode.GENERAL_ERROR)
    for note in notes:
        print(f"hop3: {note}", file=sys.stderr)


def verify_authentication(config: Config) -> None:
    """
    Verify that the current authentication token is valid.

    Makes a lightweight auth whoami call to check if the token works.

    Args:
        config: The CLI configuration

    Raises:
        AuthenticationError: If authentication is invalid or verification fails.
    """
    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["auth", "whoami"])
            match response:
                case Ok():
                    return
                case Error(message=message):
                    msg = f"Authentication failed: {message}"
                    raise AuthenticationError(msg)
                case _ as unreachable:
                    assert_never(unreachable)
    except AuthenticationError:
        raise
    except Exception as e:
        msg = f"Authentication verification failed: {e}"
        raise AuthenticationError(msg) from e
