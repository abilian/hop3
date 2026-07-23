# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Collision-safe run-ids and artifact directories for diagnostic bundles.

A bundle's ``run_id`` is ``<ISO>-<app>-<shortid>`` (ADR 043 §7.3). The ISO
timestamp is colon-free so it is filesystem-safe; the short hex suffix dedupes
sub-second collisions of the same app; ``make_bundle_dir``'s
``mkdir(exist_ok=False)`` retry is the hard guarantee against overwriting an
existing bundle (the "two focalboard logs clobber each other" bug).
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

ISO_FMT = "%Y-%m-%dT%H-%M-%SZ"  # colon-free, filesystem-safe ISO-8601
DEFAULT_RUNS_DIR = Path.home() / ".hop3" / "test-runs"  # sibling of test-results.db

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(name: str) -> str:
    """Reduce an app name to a short, filesystem-safe slug."""
    return _SLUG_RE.sub("-", name.lower())[:40].strip("-") or "app"


def make_run_id(app: str, *, now: datetime | None = None) -> str:
    """
    Build ``<ISO>-<app>-<shortid>``.

    Under pytest-xdist the worker id is folded in so parallel writers never
    contend on the same base id.
    """
    ts = (now or datetime.now(tz=timezone.utc)).strftime(ISO_FMT)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    prefix = f"{worker}-" if worker else ""
    return f"{ts}-{_slug(app)}-{prefix}{secrets.token_hex(3)}"


def make_bundle_dir(run_id: str, base_dir: Path | None = None) -> tuple[str, Path]:
    """
    Create a unique bundle directory.

    Returns ``(final_run_id, dir)``. ``final_run_id`` may be *extended* on a
    collision and MUST be the value persisted to the store, so the on-disk
    directory basename always equals the stored run-id. Never reconstruct the
    path from a run-id; always read ``bundle_path`` back from the store.
    """
    base = base_dir or DEFAULT_RUNS_DIR
    base.mkdir(parents=True, exist_ok=True)
    rid = run_id
    for _ in range(5):
        candidate = base / rid
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return rid, candidate
        except FileExistsError:
            rid = f"{run_id}-{secrets.token_hex(2)}"
    msg = f"could not create a unique bundle dir under {base}"
    raise OSError(msg)
