# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Deprecation-alias helpers for the CLI-consistency migration (ADR 052).

The migration renames flags, env vars, and one binary. Each old name stays
accepted for one release as a deprecated alias that resolves to the new name and
prints a one-line notice to stderr — so no existing invocation breaks on the
first release (ADR 052 Migration).

Stdlib-only (``os``/``sys``): this package is bundled into the ``curl | python3``
installer and must not take a dependency.
"""

from __future__ import annotations

import os
import sys

# Warn at most once per (old) name per process — a script that passes the same
# deprecated flag/env twice shouldn't spam.
_WARNED: set[str] = set()


def warn_deprecated(old: str, new: str, *, kind: str = "option") -> None:
    """Print a one-line deprecation notice to stderr (deduped per old name)."""
    if old in _WARNED:
        return
    _WARNED.add(old)
    print(
        f"hop3: warning: the {kind} '{old}' is deprecated; use '{new}'", file=sys.stderr
    )


def env_with_alias(
    new_var: str, old_var: str, default: str | None = None
) -> str | None:
    """
    Value of ``new_var``, else ``old_var`` (with a deprecation notice), else default.

    The new name always wins when both are set — explicit-new over deprecated-old.
    """
    value = os.environ.get(new_var)
    if value is not None:
        return value
    old_value = os.environ.get(old_var)
    if old_value is not None:
        warn_deprecated(old_var, new_var, kind="environment variable")
        return old_value
    return default


def env_bool_with_alias(new_var: str, old_var: str) -> bool:
    """
    Boolean env with ``new_var`` preferred, ``old_var`` warned (see env_with_alias).

    Truthy is ``1``/``true`` (case-insensitive), matching ``common.env_bool``.
    """
    value = env_with_alias(new_var, old_var)
    return value is not None and value.strip().lower() in {"1", "true"}


def canonicalize_flags(argv: list[str], aliases: dict[str, str]) -> list[str]:
    """
    Rewrite deprecated long flags in ``argv`` to their canonical spelling.

    ``aliases`` maps ``--old`` → ``--new``. Handles both ``--old value`` (only the
    flag token is rewritten; the following value is untouched) and ``--old=value``
    (rewritten to ``--new=value``). A deprecated flag present triggers one stderr
    notice. Tokens that are not deprecated flags pass through unchanged.

    Long flags only — the renames in ADR 052 are all long flags, and rewriting a
    bare value that happens to look like a short-flag cluster would be unsafe.
    """
    out: list[str] = []
    for token in argv:
        name, sep, rest = token.partition("=")
        new = aliases.get(name)
        if new is not None:
            warn_deprecated(name, new)
            out.append(f"{new}{sep}{rest}" if sep else new)
        else:
            out.append(token)
    return out


def warn_deprecated_flags(argv: list[str], aliases: dict[str, str]) -> None:
    """
    Warn (once each) for any deprecated flag present in ``argv`` — no rewrite.

    Unlike :func:`canonicalize_flags`, this only emits the notice; the old option
    strings stay registered on the parser so they still parse. Use it when the
    canonical spelling takes a value the old one didn't (``--git`` → ``--from
    git``) or when the old name is an argparse alias on the same argument
    (``--ssh-key`` → ``--identity``), where a token rewrite can't help. ``aliases``
    maps ``--old`` → the human suggestion (e.g. ``--from git``).
    """
    for token in argv:
        name = token.partition("=")[0]
        new = aliases.get(name)
        if new is not None:
            warn_deprecated(name, new)
