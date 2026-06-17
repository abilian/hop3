# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Alias mechanism (ADR 036 D9).

An alias is a client-side *first-token rewrite*: before dispatching a command,
we look up the first token in a table and, if matched, replace it with a
sequence of tokens. The rest of argv follows unchanged.

Per ADR 036 D9:
- Three sources form a **disjoint union** (no shadowing): built-in core
  aliases, plugin-registered aliases, and user aliases from
  `~/.config/hop3-cli/config.toml [aliases]`. Collisions cause the
  later-loaded entry to be skipped with a warning (enforced in
  `hop3_cli.core.alias_registry`).
- **Prefix aliases** are supported: an alias can rewrite the first N tokens
  to produce a different command path (e.g., `pg` → `addon postgres` means
  `hop3 pg diagnose mydb` expands to `hop3 addon postgres diagnose mydb`).
- **Collision-with-subcommand rule**: if the expanded form would clobber a
  user's intent (they typed `hop3 addons create foo` meaning the plural form
  of the namespace, not `addon list create foo`), we refuse to fire when the
  token after the alias is itself a known subcommand of the namespace the
  alias expands to. This check uses the cached command list from
  `hop3_cli/commands/local/completion_cmd.py` when available.

Representation: each alias maps a source token (or a short prefix of tokens)
to its expansion as a tuple of tokens. Expansions are static text — no
variable interpolation, no shell substitution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AliasSource = Literal["built-in", "plugin", "user"]


@dataclass(frozen=True)
class Alias:
    """A single alias entry."""

    source_token: str
    # Expansion: tuple of tokens to substitute in place of the source token.
    expansion: tuple[str, ...]
    # Where this alias was defined.
    origin: AliasSource
    # Optional: if the alias was loaded from a file, the file path (for
    # diagnostic output in `hop3 aliases` and collision warnings).
    origin_detail: str = ""


# Built-in core aliases (ADR 036 D9, initial table).
# Order here doesn't matter — the resolver uses dict lookup.
CORE_ALIASES: tuple[Alias, ...] = (
    # Plural list shortcuts
    Alias("apps", ("app", "list"), "built-in"),
    Alias("addons", ("addon", "list"), "built-in"),
    Alias("plugins", ("plugin", "list"), "built-in"),
    Alias("ports", ("port", "list"), "built-in"),
    Alias("networks", ("network", "list"), "built-in"),
    # Cross-platform synonyms.
    # Note: `env` is now a real command group (was an alias for `config show`);
    # `config` is the back-compat alias, registered server-side on each env
    # command (hop3/commands/config.py). `hop3 config set ...` still works.
    Alias("whoami", ("auth", "whoami"), "built-in"),
    # Note: `login` and `logout` are NOT aliases here. They are LOCAL commands
    # (packages/hop3-cli/src/hop3_cli/commands/local/login_cmd.py) that handle
    # SSH-based auth flows locally with side effects (token fetch, config
    # write). They are NOT simply `auth login` forwarded to the server, so
    # aliasing them would break local behavior. Users who want to hit the
    # server's auth commands explicitly can type `hop3 auth login` /
    # `hop3 auth logout`.
)
