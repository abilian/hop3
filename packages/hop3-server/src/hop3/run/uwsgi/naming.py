# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The one place that knows how a uWSGI vassal ``.ini`` is named.

A vassal file is ``{app}_{kind}.{ordinal}.ini``. The underscore is a
**boundary**, not decoration: without it, an app-scoped sweep for ``wiki``
also matches ``wiki-js_web.1.ini``, so stopping or destroying one app rips
the vassal config out from under a different, unrelated app — a leftover
that presents as an order-dependent heisenbug in whichever app is deployed
next.

``run/reaper.py`` enforces the same boundary for *processes*; this module is
its filesystem twin. Both the writer and every app-scoped sweep go through
here so the rule has a single representation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["vassal_glob", "vassal_name"]


def vassal_name(app_name: str, kind: str, ordinal: int) -> str:
    """The vassal filename for one worker of an app."""
    return f"{app_name}_{kind}.{ordinal}.ini"


def vassal_glob(app_name: str) -> str:
    """
    Glob matching every vassal belonging to ``app_name`` — and nothing else.

    The trailing underscore is what stops ``wiki`` from matching
    ``wiki-js_web.1.ini``.
    """
    return f"{app_name}_*.ini"


def worker_env_path(app_path: Path, kind: str, ordinal: int) -> Path:
    """
    Where one worker's environment, every secret in it, is written (0600).

    One definition for the worker that writes it and the scale-down that
    removes it: a removed worker's file stayed on disk, a copy of the secrets
    that a later rotation did not update.
    """
    return app_path / "worker-env" / f"{kind}.{ordinal}.env"
