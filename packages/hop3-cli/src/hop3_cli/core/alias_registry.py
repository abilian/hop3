# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Alias registry: loads all alias sources and resolves commands (ADR 036 D9).

Responsibilities:
- Build the effective alias table by merging core + plugin + user aliases,
  enforcing the disjoint-union rule (no shadowing).
- Resolve a single argv-style `list[str]` through the alias table, applying
  the collision-with-subcommand rule.

Collision handling (D9):
- Two sources claim the same token: the first source (by load order: core
  first, then plugins, then user) wins. Later sources are *skipped* with a
  warning the caller can surface to the user (via `skipped_user_aliases`).
- An alias would fire but the token after it is a known subcommand of the
  target namespace: skip this invocation's rewrite (not the alias entry
  itself — other invocations might still fire).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from .aliases import CORE_ALIASES, Alias


@dataclass
class AliasRegistry:
    """Effective alias table and diagnostic info for `hop3 aliases`."""

    # All accepted aliases, keyed by source_token.
    aliases: dict[str, Alias] = field(default_factory=dict)
    # User aliases that were skipped because they'd collide with a core or
    # plugin alias (ADR 036 D9: no shadowing). Format: (token, reason).
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def find(self, token: str) -> Alias | None:
        return self.aliases.get(token)


def load_user_aliases_from_config(config_file: Path | None) -> list[Alias]:
    """Load user aliases from `~/.config/hop3-cli/config.toml [aliases]`.

    Each key maps to an expansion string. The string is split on whitespace
    to produce the expansion tuple, so `pg = "addon postgres"` becomes
    `("addon", "postgres")`.

    Returns an empty list if the config file is missing or has no [aliases]
    section. Unparseable config is silently skipped here; use
    ``load_user_aliases_with_diagnostics`` if you want the parse errors and
    rejected entries surfaced (``hop3 aliases`` does).
    """
    aliases, _ = load_user_aliases_with_diagnostics(config_file)
    return aliases


@dataclass
class AliasLoadDiagnostics:
    """Non-fatal problems encountered while loading user aliases."""

    # Top-level parse failure: TOML decode error or unreadable file.
    parse_error: str | None = None
    # Per-entry rejections: (key, reason) for entries that were dropped.
    rejected: list[tuple[str, str]] = field(default_factory=list)


def load_user_aliases_with_diagnostics(
    config_file: Path | None,
) -> tuple[list[Alias], AliasLoadDiagnostics]:
    """Same as ``load_user_aliases_from_config`` but also returns diagnostics.

    Used by ``hop3 aliases`` so users see *why* an alias they wrote isn't
    showing up. Day-to-day CLI invocations stay quiet to avoid one warning
    per invocation when a config is half-broken.
    """
    diags = AliasLoadDiagnostics()
    if config_file is None or not config_file.is_file():
        return [], diags
    try:
        data = tomllib.loads(config_file.read_text())
    except OSError as e:
        diags.parse_error = f"could not read {config_file}: {e}"
        return [], diags
    except tomllib.TOMLDecodeError as e:
        diags.parse_error = f"TOML parse error in {config_file}: {e}"
        return [], diags

    raw = data.get("aliases", {})
    if not isinstance(raw, dict):
        diags.parse_error = (
            f"[aliases] section in {config_file} must be a table, "
            f"got {type(raw).__name__}"
        )
        return [], diags

    out: list[Alias] = []
    origin_detail = str(config_file)
    for token, expansion_str in raw.items():
        if not isinstance(token, str):
            diags.rejected.append((repr(token), "alias name must be a string"))
            continue
        if not isinstance(expansion_str, str):
            diags.rejected.append((
                token,
                f"expansion must be a string, got {type(expansion_str).__name__}",
            ))
            continue
        tokens = tuple(expansion_str.split())
        if not tokens:
            diags.rejected.append((token, "expansion is empty"))
            continue
        out.append(
            Alias(
                source_token=token,
                expansion=tokens,
                origin="user",
                origin_detail=origin_detail,
            )
        )
    return out, diags


def build_registry(
    user_aliases: list[Alias] | None = None,
    plugin_aliases: list[Alias] | None = None,
    *,
    warn_to_stderr: bool = False,
) -> AliasRegistry:
    """Build the effective alias registry (disjoint union, no shadowing).

    Load order (earlier wins on collision):
      1. Core built-in aliases
      2. Plugin-registered aliases
      3. User aliases

    If `warn_to_stderr` is True, print a single warning line listing any
    skipped user aliases. (The CLI calls this only for bare `hop3` to avoid
    noise on every invocation per ADR D9.)
    """
    registry = AliasRegistry()

    # Layer 1: core
    for alias in CORE_ALIASES:
        registry.aliases[alias.source_token] = alias

    # Layer 2: plugins (when we have them — for now, empty)
    for alias in plugin_aliases or []:
        if alias.source_token in registry.aliases:
            existing = registry.aliases[alias.source_token]
            # Plugin collision against core — skip the plugin's entry.
            registry.skipped.append((
                alias.source_token,
                f"plugin alias collides with {existing.origin} alias",
            ))
            continue
        registry.aliases[alias.source_token] = alias

    # Layer 3: user aliases
    for alias in user_aliases or []:
        if alias.source_token in registry.aliases:
            existing = registry.aliases[alias.source_token]
            registry.skipped.append((
                alias.source_token,
                f"user alias shadows {existing.origin} alias (skipped)",
            ))
            continue
        registry.aliases[alias.source_token] = alias

    if warn_to_stderr and registry.skipped:
        tokens = ", ".join(t for t, _ in registry.skipped)
        print(
            f"warning: skipped user aliases due to collisions: {tokens}",
            file=sys.stderr,
        )
        print(
            "(Run `hop3 aliases` to see details.)",
            file=sys.stderr,
        )

    return registry


def resolve_aliases(
    cli_args: list[str],
    registry: AliasRegistry,
    *,
    known_subcommands_of_namespace: dict[str, set[str]] | None = None,
) -> tuple[list[str], Alias | None]:
    """Expand an alias at the start of cli_args, per D9's collision rule.

    Args:
        cli_args: The argv (after flag stripping), e.g. ["apps"] or ["env", "myapp"].
        registry: The effective alias registry.
        known_subcommands_of_namespace: Optional map {namespace_token -> set of
            known subcommand tokens}. When provided, we refuse to fire the
            alias if the next token after the alias is a known subcommand of
            the target namespace — this preserves user intent for typos like
            `hop3 addons create foo` (meaning `hop3 addon create foo`, not
            `hop3 addon list create foo`).

    Returns:
        (rewritten_args, alias_that_fired_or_None)
    """
    if not cli_args:
        return cli_args, None

    first = cli_args[0]
    alias = registry.find(first)
    if alias is None:
        return cli_args, None

    # Check the collision-with-subcommand rule.
    if known_subcommands_of_namespace is not None and len(cli_args) >= 2:
        next_token = cli_args[1]
        # Find the namespace token in the expansion (usually expansion[0]).
        namespace = alias.expansion[0] if alias.expansion else ""
        subs = known_subcommands_of_namespace.get(namespace, set())
        if next_token in subs:
            # Refuse to fire — user most likely meant the singular namespace form.
            return cli_args, None

    rewritten = list(alias.expansion) + cli_args[1:]
    return rewritten, alias


def build_subcommand_index(command_names: list[str]) -> dict[str, set[str]]:
    """From a list of space-separated command names, build a map of
    `{namespace -> {subcommand_verbs}}` for the collision-with-subcommand check.

    Example input: ["app list", "app create", "app destroy", "apps", "addon list", ...]
    Example output: {"app": {"list", "create", "destroy"}, "addon": {"list"}, ...}
    """
    index: dict[str, set[str]] = {}
    for name in command_names:
        tokens = name.split()
        if len(tokens) >= 2:
            ns, verb = tokens[0], tokens[1]
            index.setdefault(ns, set()).add(verb)
    return index


def cached_subcommand_index() -> dict[str, set[str]]:
    """Load the subcommand index from the completion cache if available.

    Falls back to a static subset sufficient for the core alias set. This
    keeps alias resolution robust even on first-run (cache cold).
    """
    # Try the cache that `hop3 completion --refresh` writes.
    cache = (
        Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        / "hop3"
        / "commands.txt"
    )
    if cache.is_file():
        try:
            names = [
                line.strip() for line in cache.read_text().splitlines() if line.strip()
            ]
            return build_subcommand_index(names)
        except OSError:
            pass

    # Static fallback: subcommand sets for the namespaces that core aliases target.
    # These are the names we documented in the command catalog.
    return {
        "app": {
            "create",
            "destroy",
            "rename",
            "show",
            "list",
            "launch",
            "sbom",
            "env",
            "debug",
            "ping",
            "build-logs",
            "migrate",
            "start",
            "stop",
            "restart",
        },
        "addon": {
            "list",
            "create",
            "destroy",
            "attach",
            "detach",
            "show",
            "status",
            "console",
            "tunnel",
            "credentials",
            "logs",
            "wait",
            "backup",
        },
        "config": {
            "show",
            "get",
            "set",
            "unset",
            "live",
            "migrate",
        },
        "auth": {
            "login",
            "logout",
            "whoami",
            "register",
            "magic-link",
        },
        "plugin": {"list", "show", "install", "uninstall"},
        "backup": {"create", "list", "show", "restore", "destroy"},
        "context": {"list", "show", "use", "add", "remove", "rename"},
        "user": {
            "add",
            "remove",
            "show",
            "list",
            "enable",
            "disable",
            "grant-admin",
            "revoke-admin",
            "set-password",
            "generate-token",
        },
        "system": {
            "check",
            "info",
            "status",
            "uptime",
            "ps",
            "logs",
            "cleanup",
        },
    }
