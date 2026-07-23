# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Deprecation notices for the hop3-test CLI (ADR 052 Migration).

Old command/flag spellings stay accepted for one release and print a one-line
stderr notice pointing at the canonical name. hop3-testing deliberately does not
import hop3-installer, so this mirrors that package's warn_deprecated locally.
"""

from __future__ import annotations

import click

# Warn at most once per (old) name per process — a repeated deprecated spelling
# shouldn't spam.
_WARNED: set[str] = set()


def warn_deprecated(old: str, new: str, *, kind: str = "option") -> None:
    """Print a one-line deprecation notice to stderr (deduped per old name)."""
    if old in _WARNED:
        return
    _WARNED.add(old)
    click.echo(
        f"hop3: warning: the {kind} '{old}' is deprecated; use '{new}'", err=True
    )
