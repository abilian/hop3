# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Catalog ↔ tested-source operations: drift check and promotion.

A catalog app's deployable recipe (`hop3.toml` + everything under `scripts/`)
must be byte-identical to its tested source under `apps/real-apps-native/<app>/`
(the only profile the catalog ships today — see ADR 057 / plan 11). The
catalog-only presentation overlay (`catalog.toml`, `readme*.md`, `icon.*`,
`screenshots/`) is authored in the catalog and is never touched here.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SOURCE_VARIANT = "apps/real-apps-native"


def find_repo_root(start: Path | None = None) -> Path:
    """
    Walk up from ``start`` (or cwd) to the hop3 repo root.

    The marker is the tested-source variant dir; falls back to the dev layout
    (this file lives at ``packages/hop3-tooling/src/hop3_tooling/``).
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / SOURCE_VARIANT).is_dir():
            return candidate
    return Path(__file__).resolve().parents[4]


def default_source_root() -> Path:
    return find_repo_root() / SOURCE_VARIANT


def default_catalog_apps() -> Path:
    """The sibling catalog checkout's ``apps/`` dir (…/hop3-catalog/apps)."""
    return find_repo_root().parent / "hop3-catalog" / "apps"


def recipe_files(app_dir: Path) -> dict[str, bytes]:
    """
    The deployable recipe as {relative-path: bytes}: hop3.toml + scripts/**.

    Excludes the catalog overlay by only ever reading hop3.toml and scripts/.
    """
    files: dict[str, bytes] = {}
    top = app_dir / "hop3.toml"
    if top.is_file():
        files["hop3.toml"] = top.read_bytes()
    scripts = app_dir / "scripts"
    if scripts.is_dir():
        for f in sorted(scripts.rglob("*")):
            if f.is_file():
                files[str(f.relative_to(app_dir))] = f.read_bytes()
    return files


def compare_app(catalog_app: Path, source_app: Path) -> list[str]:
    """Drift descriptions for one app (empty list == in sync)."""
    if not source_app.is_dir():
        return [f"no tested source at {source_app}"]
    cat = recipe_files(catalog_app)
    src = recipe_files(source_app)
    issues: list[str] = []
    for path in sorted(set(cat) | set(src)):
        if path not in src:
            issues.append(f"catalog-only recipe file (not in tested source): {path}")
        elif path not in cat:
            issues.append(f"missing in catalog: {path}")
        elif cat[path] != src[path]:
            issues.append(f"differs from tested source: {path}")
    return issues


def promote_app(app_id: str, source_root: Path, catalog_apps: Path) -> None:
    """
    Copy one tested recipe into the catalog verbatim (overlay untouched).

    Replaces the catalog copy's ``hop3.toml`` and mirrors its ``scripts/`` (so a
    stale script is removed). ``catalog.toml``, readmes, and icons are left as-is.
    """
    src = source_root / app_id
    # Promote in place: an existing recipe keeps the status it earned, and a new
    # one starts at `alpha` rather than being published by the act of copying it.
    dst = app_dirs(catalog_apps).get(app_id, catalog_apps / "alpha" / app_id)
    if not (src / "hop3.toml").is_file():
        msg = f"no tested source recipe at {src / 'hop3.toml'}"
        raise FileNotFoundError(msg)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / "hop3.toml", dst / "hop3.toml")

    dst_scripts = dst / "scripts"
    if dst_scripts.exists():
        shutil.rmtree(dst_scripts)
    if (src / "scripts").is_dir():
        shutil.copytree(src / "scripts", dst_scripts)


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
