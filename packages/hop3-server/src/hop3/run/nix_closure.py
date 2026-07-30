# Copyright (c) 2023-2026, Abilian SAS

"""
Locating `nix-store`, and checking that a Nix app's runtime closure is intact.

A Nix wrapper execs hardcoded `/nix/store` paths. If a garbage collection
reclaims any path in that closure, the worker dies with "No such file or
directory" and the operator sees only a health-check timeout minutes later.
Checking the closure at deploy time turns that into an immediate, named error.

`nix-store` is deliberately resolved by **absolute path** rather than through
`PATH`. The deploy process does not run under a login shell, so the Nix profile
is not sourced and `nix-store` is not on `PATH` even on a host where Nix is
installed and working — which is how the original guard came to log a skip on
every deploy and never fire once.

Both installation modes have to be covered, because the installer picks between
them by environment: **multi-user** (daemon) where systemd is available, and
**single-user** in containers and other non-systemd targets. The single-user
profile lives under the *hop3 user's* home, which is not the deploy process's
`$HOME` — expanding `~` here would repeat the original mistake in a new place.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from hop3.config import HOP3_ROOT

__all__ = [
    "NIX_STORE_CANDIDATES",
    "ClosureCheckError",
    "missing_closure_paths",
    "resolve_nix_store",
]

# Multi-user (daemon) install first: the installer prefers it wherever systemd is
# available, and it is readable whichever user the deploy runs as. Then the
# single-user profile, resolved against the **hop3 user's** home rather than the
# current process's — in a container the installer falls back to single-user and
# installs there, while the deploy may be running as root.
NIX_STORE_CANDIDATES: tuple[str, ...] = (
    "/nix/var/nix/profiles/default/bin/nix-store",
    f"{HOP3_ROOT}/.nix-profile/bin/nix-store",
    "/run/current-system/sw/bin/nix-store",
)

CLOSURE_QUERY_TIMEOUT_SECONDS = 60


class ClosureCheckError(Exception):
    """The closure could not be checked. Never raised for a *broken* closure.

    Separating "the closure is broken" from "the check could not run" matters:
    the first is an application problem the operator fixes by redeploying, the
    second is a platform problem, and reporting one as the other sends the
    operator to the wrong place.
    """


def resolve_nix_store() -> Path | None:
    """Absolute path to a usable `nix-store`, or None if there is none."""
    for candidate in NIX_STORE_CANDIDATES:
        path = Path(os.path.expanduser(candidate))
        if path.is_file() and os.access(path, os.X_OK):
            return path
    # Last resort. On a correctly-installed host one of the candidates hits;
    # this covers unusual layouts rather than being the expected path.
    found = shutil.which("nix-store")
    return Path(found) if found else None


def missing_closure_paths(roots: list[str], nix_store: Path) -> list[str]:
    """Store paths referenced by `roots` that no longer exist on disk.

    Returns an empty list when every path in every closure is present.

    Raises:
        ClosureCheckError: the query could not be completed, so the closure's
            state is unknown. The caller must treat this as a failure rather
            than as an all-clear.
    """
    missing: list[str] = []
    for root in roots:
        if not os.path.exists(root):
            missing.append(root)
            continue
        try:
            result = subprocess.run(
                [str(nix_store), "-q", "--requisites", root],
                capture_output=True,
                text=True,
                timeout=CLOSURE_QUERY_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            msg = f"querying the closure of {root} failed: {e}"
            raise ClosureCheckError(msg) from e
        if result.returncode != 0:
            detail = result.stderr.strip()[:200]
            msg = (
                f"`nix-store -q --requisites {root}` exited "
                f"{result.returncode}: {detail}"
            )
            raise ClosureCheckError(msg)
        missing.extend(p for p in result.stdout.split() if p and not os.path.exists(p))
    return missing
