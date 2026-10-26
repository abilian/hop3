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
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, assert_never

if TYPE_CHECKING:
    from collections.abc import Iterator

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
    serve_offline_help,
)
from .commands.arguments import describe_archive
from .commands.local.shell_cmd import intercept_app_shell
from .config import Config, get_config
from .core.alias_registry import (
    build_registry,
    cached_subcommand_index,
    load_user_aliases_from_config,
    resolve_aliases,
)
from .core.app_scope import EXPLICIT_APP_COMMANDS, RUN_COMMANDS, is_app_scoped
from .core.deploy_preview import (
    build_plan,
    domain_target_warnings,
    render_plan,
)
from .core.project_guard import check_project_mismatch
from .core.resolution import (
    format_context_trace,
    format_trace,
    resolve_app,
    resolve_context,
)
from .core.target import check_project_blocks, resolve_target
from .core.workspace_guard import check_workspace_dependency
from .exceptions import AuthenticationError, CliError, TargetError
from .exit_codes import ExitCode, map_message_to_exit, map_rpc_code_to_exit
from .rpc import Client, handle_response
from .rpc.errors import PROTECTED_NEEDS_CONFIRMATION, PROTECTED_NEEDS_EXPLICIT
from .ui import (
    RichPrinter,
    err,
    show_unauthenticated_message,
)
from .ui.prompts import is_no_input

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
    # ADR 042: decide where this invocation goes, once, before anything
    # dispatches. A refusal is recorded and raised only by a command that
    # needs a server, so `hop3 context use` still runs in an unbound checkout.
    context_resolution = _wire_target(flags, config)

    if flags.verbosity >= 2:
        _print_debug_info(printer, cli_args, config, flags)

    cli_args = cli_args or ["help"]

    # ADR 036 D9: expand aliases before local/server dispatch, unless the user
    # passed --no-alias. Aliases fire on the first token only and respect the
    # collision-with-subcommand rule.
    if not flags.no_alias:
        cli_args = _apply_aliases(cli_args, config, printer, flags)

    # `tunnel` is dispatched locally (it forwards a port from THIS machine) but
    # it connects to the server for the addon endpoint, so it says where.
    wants_help = bool({"--help", "-h"} & set(cli_args))
    if cli_args[:1] == ["tunnel"] and not flags.why and not wants_help:
        _reach_target(config, flags)

    # Handle local commands (init, config) that don't need server
    if is_local_command(cli_args):
        if flags.verbosity >= 2:
            printer.print_debug("Handling as local command")
        if handle_local_command(cli_args, config, printer):
            return

    cli_args = handle_help_flags(cli_args)

    # Help must work before the CLI has a server to ask (ADR 036 M9.3).
    if serve_offline_help(cli_args, config):
        return

    app_resolution = _compute_app_resolution(cli_args, flags, context_resolution)

    if flags.why:
        # Always print the resolution trace to stderr, regardless of verbosity
        # or json_output setting. `--why` is an explicit user request for
        # diagnostic output and shouldn't be gated.
        _print_why(config, context_resolution, app_resolution)
        sys.exit(ExitCode.SUCCESS)

    cli_args = _inject_resolved_app(cli_args, flags, app_resolution, printer)
    _reach_target(config, flags)
    # `app shell` is the one command that never goes over RPC: it needs a
    # terminal, so the CLI opens it over ssh itself, with the app resolved
    # like any other app-scoped command.
    intercept_app_shell(cli_args, config)
    _check_project_mismatch(cli_args, flags, app_resolution)
    _check_workspace_dependency(cli_args, flags)
    cli_args = _forward_dry_run(cli_args, flags)
    _handle_deploy_preview(cli_args, flags, config, app_resolution)
    _update_printer_scope(printer, config, cli_args)
    _check_prerequisites(cli_args, config, printer, flags)

    if flags.verbosity >= 2:
        printer.print_debug("Executing RPC command...")

    deploy_override = _context_deploy_override(cli_args, config)
    extra_args = _get_extra_args_safe(
        cli_args,
        flags.verbosity,
        hop3_toml_override=deploy_override,
        json_output=flags.json_output,
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
    config.set_assume_yes(flags.skip_confirm)


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


def _wire_target(flags: CliFlags, config: Config) -> ContextResolution:
    """Resolve this invocation's target (ADR 042) and record it on the config."""
    resolution = resolve_context(
        flags.context, default_context=config.get_default_context()
    )
    try:
        config.set_target(resolve_target(resolution, config))
    except TargetError as e:
        config.set_target_error(e)
    return resolution


def _reach_target(config: Config, flags: CliFlags) -> None:
    """
    About to reach the server: refuse without a target, else say where (rule C).

    The line goes to stderr, so it never mixes into output a script parses;
    ``--quiet`` silences it.
    """
    target = config.require_target()
    if not flags.quiet:
        print(target.describe(), file=sys.stderr)
    if flags.via_ssh:
        _force_bootstrap_route(config)


def _print_why(
    config: Config,
    context_resolution: ContextResolution,
    app_resolution: AppResolution | None,
) -> None:
    """The ``--why`` trace: how the context, the server and the app were chosen."""
    print(format_context_trace(context_resolution), file=sys.stderr)
    try:
        print(f"  {config.require_target().describe()}", file=sys.stderr)
    except TargetError as e:
        print(f"  refused: {e}", file=sys.stderr)
    if app_resolution is not None:
        print(format_trace(app_resolution), file=sys.stderr)


def _force_bootstrap_route(config: Config) -> None:
    """
    Send this one invocation through the context's SSH route (``--via-ssh``).

    The rescue path. Everyday traffic goes to the context's ``server``; this is
    for when that is precisely what is broken — an expired certificate, a proxy
    that is down, DNS pointing somewhere else. It refuses rather than quietly
    using the ordinary route, which would look like the flag did nothing.
    """
    target = config.get_bootstrap_target()
    if not target:
        print(
            "Error: --via-ssh, but this target has no SSH bootstrap route.\n"
            "  It was recorded by a token or password login, which cannot know "
            "one.\n"
            "  Sign in over SSH once to record it: hop3 login <user>@<host>",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)
    config.set_active_server(f"ssh://{target}")


def _compute_app_resolution(
    cli_args: list[str], flags: CliFlags, context_resolution: ContextResolution
) -> AppResolution | None:
    """
    Resolve the app for an app-scoped command, or for ``--why``; else None.

    The selected context supplies app source #5 (``[contexts.<sel>].app``),
    trusted per how the context was selected.
    """
    scoped, _ = is_app_scoped(cli_args)
    if scoped or flags.why:
        return resolve_app(cli_app=flags.app, context=context_resolution)
    return None


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
    # an AMBIENT app must never be substituted as that name: without --app, the
    # server's own "requires --app" guard fires loudly rather than installing
    # under whatever app the current directory resolves to. Listings (`addon
    # list`) take --app as a filter, and bare means "everything".
    if not flags.app and tuple(cli_args[:n_consumed]) in EXPLICIT_APP_COMMANDS:
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


def _forward_dry_run(cli_args: list[str], flags: CliFlags) -> list[str]:
    """
    Hand ``--dry-run`` back to the command it was typed for.

    ``parse_flags`` consumes the flag for ``deploy``, whose plan the client
    prints itself. Every other command gets it back: one that previews
    (``system cleanup``, ``admin reencrypt-credentials``) previews, and one
    that cannot refuses the unknown flag. Dropping it instead, with a warning,
    made ``hop3 system cleanup --dry-run`` prune for real.
    """
    if not flags.dry_run or cli_args[:1] == ["deploy"]:
        return cli_args
    if tuple(cli_args[:1]) in RUN_COMMANDS or tuple(cli_args[:2]) in RUN_COMMANDS:
        # Appended, it would land on the program's own command line.
        print(
            "Error: `hop3 run` has no --dry-run; a flag for the program goes "
            "after the program's name.",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)
    return [*cli_args, "--dry-run"]


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

    target = config.require_target()
    source_path = _deploy_source_path(cli_args)
    plan = build_plan(
        source_path=source_path,
        context=target.context,
        app=app_resolution.app or "",
        server=config.get_api_url(),
        context_source=target.source.value,
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


def _context_deploy_override(cli_args: list[str], config: Config) -> bytes | None:
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
    if "contexts" not in raw:
        return None  # nothing to merge or strip — upload the file as-is
    target = config.require_target()
    # The source may be another directory than the one the target was
    # resolved in (`hop3 deploy ../other`): its blocks follow the same rule.
    check_project_blocks(own, target.context)
    effective = flatten_for_context(raw, target.context)
    return toml.dumps(effective).encode("utf-8")


def _get_extra_args_safe(
    cli_args: list[str],
    verbosity: int,
    hop3_toml_override: bytes | None = None,
    *,
    json_output: bool = False,
) -> dict:
    """Get extra args with error handling."""
    try:
        return get_extra_args(
            cli_args,
            verbosity=verbosity,
            hop3_toml_override=hop3_toml_override,
            json_output=json_output,
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

    # Check authentication - try auto-auth via SSH if not authenticated
    if not config.is_authenticated():
        try:
            _try_auto_authenticate(config, printer)
        except AuthenticationError:
            show_unauthenticated_message(config)
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
                show_unauthenticated_message(config)
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
    Mint a token over the context's SSH bootstrap route, if it has one.

    Raises:
        AuthenticationError: If auto-auth is not available or fails.
    """
    from hop3_cli.core.auto_auth import (  # ruff:ignore[import-outside-top-level]
        auto_authenticate,
    )

    if not config.get_api_url():
        msg = "No API URL configured"
        raise AuthenticationError(msg)

    try:
        target = auto_authenticate(config)
    except AuthenticationError as e:
        if printer.verbosity >= 1:
            printer.print_debug(f"Auto-auth failed: {e}")
        raise

    if printer.verbosity >= 1:
        printer.print_debug(f"Auto-authenticated via SSH to {target}")


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
            with _transport_errors_reported(client):
                validated_extra_args: dict[str, Any] = {
                    k: v
                    for k, v in extra_args.items()
                    if isinstance(k, str) and v is not None
                }
                response = client.rpc("cli", cli_args, **validated_extra_args)
                if kind := _protected_kind(response):
                    # Remembered, so `hop3 context use` can say so.
                    config.mark_context_protected(config.require_target().context)
                # ponytail: the refused call is resent whole, so a deploy to a
                # protected server uploads its archive twice; learn the mark
                # up front (it is cached on the context) if that ever matters.
                if kind == PROTECTED_NEEDS_CONFIRMATION:
                    _confirm_protected_change(cli_args, config)
                    client.protected_confirmed = True
                    response = client.rpc("cli", cli_args, **validated_extra_args)

                # Get tunnel port if using SSH tunnel (for streaming support)
                tunnel_port = None
                if client.tunnel:
                    tunnel_port = client.tunnel.local_bind_port

                # Handle response INSIDE the context to keep tunnel alive for
                # streaming
                handle_response(
                    response, cli_args, config, printer, tunnel_port=tunnel_port
                )
        except Exception as e:
            err(f"Error while executing command:\n{e}")
            sys.exit(ExitCode.GENERAL_ERROR)


def _protected_kind(response: object) -> str | None:
    """The protected-server refusal ``response`` carries (ADR 042, D), if any."""
    if not isinstance(response, Error) or not isinstance(response.data, dict):
        return None
    kind = response.data.get("kind")
    if kind in {PROTECTED_NEEDS_CONFIRMATION, PROTECTED_NEEDS_EXPLICIT}:
        return kind
    return None


def _confirm_protected_change(cli_args: list[str], config: Config) -> None:
    """
    Ask for the app's name, typed, before changing a protected server.

    The server sent the question only because the command named the server
    explicitly (``-c`` or ``HOP3_CONTEXT``), so ``--yes`` may answer it: a CI
    job names its target in its own script. Without a terminal, refuse.
    """
    target = config.require_target()
    if config.assume_yes():
        return
    app = _app_flag_value(cli_args)
    expected = app or target.context
    what = f"the app's name ({app})" if app else f"the context's name ({expected})"
    if is_no_input() or not sys.stdin.isatty():
        err(
            f"{target.context} ({target.server}) is protected: confirm by typing "
            f"{what}, or re-run with --yes."
        )
        sys.exit(ExitCode.CONFIRMATION_DECLINED)
    typed = input(
        f"{target.context} ({target.server}) is protected. Type {what} to confirm: "
    )
    if typed.strip() != expected:
        err("That does not match; nothing was changed.")
        sys.exit(ExitCode.CONFIRMATION_DECLINED)


def _app_flag_value(cli_args: list[str]) -> str | None:
    """The value of the ``--app`` the CLI injected or the user typed, if any."""
    for i, arg in enumerate(cli_args[:-1]):
        if arg in {"--app", "-a"}:
            return cli_args[i + 1]
    return None


@contextmanager
def _transport_errors_reported(client: Client) -> Iterator[None]:
    """Report a failure to reach the server as what it is, and exit."""
    try:
        yield
    except requests.exceptions.SSLError:
        _handle_ssl_error(client.rpc_url)
    except requests.exceptions.ConnectionError as e:
        if client.tunnel:
            _handle_connection_error(
                e, client.api_url, ssh_stderr=client.tunnel.stderr_tail
            )
        _handle_connection_error(e, client.rpc_url)
    except requests.exceptions.HTTPError as e:
        err(f"HTTP error while connecting to the Hop3 server:\n{e}")
        sys.exit(ExitCode.NETWORK_ERROR)
    except (TimeoutError, requests.exceptions.Timeout) as e:
        # requests' ReadTimeout is neither of the above: it reached the
        # catch-all as "Error while executing command".
        err(f"The Hop3 server at {client.rpc_url} did not answer in time:\n  {e}")
        sys.exit(ExitCode.NETWORK_ERROR)


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


# A ConnectionError that never reached the server — as opposed to one that died
# part-way through an exchange with a server that was answering fine.
_NEVER_CONNECTED_MARKERS = ("refused", "name or service", "nodename", "unreachable")


def _handle_connection_error(
    e: Exception, rpc_url: str, *, ssh_stderr: str = ""
) -> None:
    """
    Report a transport failure with the cause it actually had.

    ``requests.ConnectionError`` covers both "nothing is listening" and "the
    exchange broke mid-flight". Answering every one of them with "Is it
    running?" states a cause we did not observe: a ``hop3 deploy`` whose upload
    timed out in ``sendall`` reported a dead server that was up the whole time.
    So the underlying error is always shown, and the is-it-running hint is
    offered only when the connection genuinely never came up.
    """
    error_str = str(e).lower()
    if "ssl" in error_str or "certificate" in error_str:
        _handle_ssl_error(rpc_url)

    message = f"Connection to the Hop3 server at {rpc_url} failed:\n  {e}"
    if ssh_stderr:
        # Over `ssh -L`, requests only sees a reset: ssh accepted the local
        # connection, then could not open the channel. ssh's stderr has why.
        message += f"\n  ssh: {ssh_stderr}"
        if "connect failed" in ssh_stderr:
            message += (
                "\nThe SSH tunnel is up but nothing answers on the remote port. "
                "Is hop3-server running there?"
            )
    elif any(marker in error_str for marker in _NEVER_CONNECTED_MARKERS):
        message += "\nIs it running?"
    err(message)
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
    from hop3_cli.core.config_migration_v3 import (  # ruff:ignore[import-outside-top-level]
        migrate_to_named_targets,
    )
    from hop3_cli.core.paths import config_dir  # ruff:ignore[import-outside-top-level]

    cfg_dir = config_dir()
    try:
        # Stage 1 (ADR 042 r1): consolidate every legacy shape into
        # config.toml [contexts.*]. Stage 2 (r2): drain those tokens into the
        # per-server store and leave config.toml secret-free. Stage 3: give the
        # unnamed default target a name and settle one current-context key.
        # Sequential — each assumes its predecessor has run.
        notes = migrate_legacy_config_042(cfg_dir)
        notes += migrate_config_to_token_store(cfg_dir)
        notes += migrate_to_named_targets(cfg_dir)
    except (MigrationError, MigrationErrorV2) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(ExitCode.GENERAL_ERROR)
    for note in notes:
        print(f"hop3: {note}", file=sys.stderr)


def _refuses_credential(code: int, message: str) -> bool:
    """The server refused the credential: by its code, or an older server's prose."""
    exits = {map_rpc_code_to_exit(code), map_message_to_exit(message)}
    return ExitCode.AUTH_ERROR in exits


def verify_authentication(config: Config) -> None:
    """
    Verify that the current authentication token is valid.

    Makes a lightweight auth whoami call to check if the token works.

    Args:
        config: The CLI configuration

    Only the server's refusal of the credential is an `AuthenticationError`.
    Anything else is reported as itself, and exits: a server too busy to answer
    within the timeout was reported as "No credential for ...", exit 4, and the
    advice to log in again.

    Raises:
        AuthenticationError: If the server refuses the credential.
    """
    with Client(config=config) as client, _transport_errors_reported(client):
        response = client.rpc("cli", ["auth", "whoami"])
    match response:
        case Ok():
            return
        case Error(code=code, message=message) if _refuses_credential(code, message):
            msg = f"Authentication failed: {message}"
            raise AuthenticationError(msg)
        case Error(code=code, message=message):
            err(f"The Hop3 server could not check your credential: {message}")
            sys.exit(map_rpc_code_to_exit(code))
        case _ as unreachable:
            assert_never(unreachable)
