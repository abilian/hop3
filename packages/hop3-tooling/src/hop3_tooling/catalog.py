# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Locating catalog recipes.

Recipes live in the catalog repository, filed by maturity
(``apps/<status>/<app>/``, ADR 059). This module answers "where is app X" for
the tools that need to read one, and is the only place that knows how the
catalog is laid out.

It used to hold the drift check and the promote step as well, on the premise
that a catalog recipe mirrored a *tested source* under ``apps/real-apps-native``
in this repository. That premise is gone: the catalog is the source now, so
there is nothing to compare it against and nothing to copy into it — the flip
plan 11 anticipated. Moving a recipe between maturities is the operation that
replaces promotion, and per ADR 059 it is earned by re-running the admitting
check rather than by copying files.
"""

from __future__ import annotations

from pathlib import Path

#: How the repo root is recognised. NOT an `apps/` directory: that was the old
#: marker (`apps/real-apps-native`), and it made root detection depend on a tree
#: that has since moved to the catalog — deleting it would have silently sent
#: every caller to the fallback path.
_ROOT_MARKER = "packages/hop3-server"


def find_repo_root(start: Path | None = None) -> Path:
    """
    Walk up from ``start`` (or cwd) to the hop3 repo root.

    Falls back to the dev layout (this file lives at
    ``packages/hop3-tooling/src/hop3_tooling/``).
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _ROOT_MARKER).is_dir():
            return candidate
    return Path(__file__).resolve().parents[4]


def default_catalog_apps() -> Path:
    """The sibling catalog checkout's ``apps/`` dir (…/hop3-catalog/apps)."""
    return find_repo_root().parent / "hop3-catalog" / "apps"


def app_dirs(catalog_apps: Path) -> dict[str, Path]:
    """
    Every catalog app directory, keyed by id, across both layouts.

    Recipes are filed under their maturity status (``apps/<status>/<app>/``,
    ADR 059); a flat ``apps/<app>/`` is still resolved so an older checkout keeps
    working. Going through here rather than joining a path matters more than it
    looks: the flat version of this function returned the *status* directories
    once the hierarchy landed, so a lint that had checked all 55 entries
    correctly reported "All 2 catalog entries are presentable".
    """
    found: dict[str, Path] = {}
    for entry in sorted(catalog_apps.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        candidates = (
            [entry]
            if (entry / "hop3.toml").is_file()
            else [
                d
                for d in sorted(entry.iterdir())
                if d.is_dir() and (d / "hop3.toml").is_file()
            ]
        )
        for d in candidates:
            found[d.name] = d
    return found


def app_ids(catalog_apps: Path) -> list[str]:
    return sorted(app_dirs(catalog_apps))


#: How a packaging variant is spelled in a catalog app id. The catalog files
#: recipes by maturity, so the *directory* no longer says how an app is built —
#: the id does, and the native build is the unsuffixed one.
VARIANT_SUFFIX = {
    "native": "",
    "nix": "-nix",
    "nix-gen": "-nixgen",
    "nix-template": "-nixgen",
    "docker": "-docker",
}


def recipe_for(app: str, variant: str, catalog_apps: Path | None = None) -> Path | None:
    """
    The recipe directory for one packaging of an application, or None.

    Callers used to build ``apps/real-apps-<variant>/<app>``, which cannot work
    once maturity decides the directory: the same recipe may sit under
    ``golden/``, ``beta/`` or ``alpha/`` and move between them as it earns or
    loses a status. So this looks the id up instead of constructing a path, and
    a promotion stops being something every caller has to know about.
    """
    if variant not in VARIANT_SUFFIX:
        return None
    catalog_apps = catalog_apps or default_catalog_apps()
    if not catalog_apps.is_dir():
        return None
    return app_dirs(catalog_apps).get(f"{app}{VARIANT_SUFFIX[variant]}")
