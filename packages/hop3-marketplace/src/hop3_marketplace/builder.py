# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Build the public catalog site (apps.hop3.cloud) from a catalog checkout.

The site and the hop3-server dashboard read the same catalog through the same
loader and taxonomy, and differ only in presentation: the dashboard installs an
app and knows which are already installed, the site shows what is available and
how to install it. Anything that changes what an app *is* belongs in
``hop3.server.catalog``, not here.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.server.catalog.loader import find_icon, find_screenshots, load_apps
from hop3.server.catalog.policy import PUBLISHABLE_STATUSES
from hop3.server.catalog.taxonomy import build_categories, build_tags

from .renderer import copy_static, generate_search_index, render_site

if TYPE_CHECKING:
    from collections.abc import Iterator


#: Served alongside the site, produced by a different step (`make stage`), and
#: fetched by every deployed hop3-server. Rendering replaces the output
#: directory wholesale, so without this a plain `hop3-site` run between two
#: releases would delete the signed catalog from the live web root and the next
#: deploy would publish its absence. Nothing would report an error; servers
#: would simply stop finding a catalog.
PRESERVED = ("catalog",)


@contextmanager
def _preserved(output_dir: Path) -> Iterator[None]:
    """Carry directories we do not own across the render that replaces them."""
    held = [name for name in PRESERVED if (output_dir / name).is_dir()]
    if not held:
        yield
        return

    with tempfile.TemporaryDirectory() as tmp:
        for name in held:
            shutil.copytree(output_dir / name, Path(tmp) / name)
        try:
            yield
        finally:
            # `finally`, not a bare yield: a render that fails halfway has
            # already emptied the output directory, and letting the exception
            # skip the restore would lose the signed catalog precisely when
            # something has gone wrong.
            for name in held:
                shutil.copytree(Path(tmp) / name, output_dir / name, dirs_exist_ok=True)


def build(catalog_apps: Path, output_dir: Path) -> int:
    """Render the catalog under ``catalog_apps`` into ``output_dir``."""
    all_apps = load_apps(catalog_apps)
    if not all_apps:
        msg = (
            f"No catalog apps under {catalog_apps}.\n"
            "Point --catalog at a catalog checkout's apps/ directory."
        )
        raise SystemExit(msg)

    # Only what the catalog publishes. `alpha`, `broken` and `retired` recipes
    # live in the repository as a record of what was tried and why it is not
    # offered (ADR 059); rendering them put a page for a known-broken app on the
    # public site, next to the working ones and indistinguishable from them.
    apps = [a for a in all_apps if a.status in PUBLISHABLE_STATUSES]
    if not apps:
        statuses = ", ".join(sorted({a.status for a in all_apps}))
        msg = (
            f"No published catalog apps under {catalog_apps}: all "
            f"{len(all_apps)} recipe(s) are at a status the catalog does not "
            f"publish ({statuses})."
        )
        raise SystemExit(msg)
    withheld = len(all_apps) - len(apps)

    # The dashboard serves images from a route; a static site serves files. The
    # loader gives paths inside each app's catalog directory; rewrite them to
    # the URLs they will be copied to below.
    for app in apps:
        if find_icon(app):
            app.icon_url = f"/assets/icons/{app.id}.webp"
        app.screenshots = [
            f"/assets/screenshots/{app.id}/{path.name}"
            for path in find_screenshots(app)
        ]

    categories = build_categories(apps)
    tags = build_tags(apps)

    with _preserved(output_dir):
        render_site(apps, categories, tags, output_dir)
    generate_search_index(apps, output_dir / "search-index.json")
    copy_static(output_dir)

    icons_dir = output_dir / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    shots_root = output_dir / "assets" / "screenshots"
    for app in apps:
        icon = find_icon(app)
        if icon:
            shutil.copy2(icon, icons_dir / f"{app.id}.webp")
        shots = find_screenshots(app)
        if shots:
            app_shots = shots_root / app.id
            app_shots.mkdir(parents=True, exist_ok=True)
            for shot in shots:
                shutil.copy2(shot, app_shots / shot.name)

    applications = sum(1 for a in apps if a.is_default_variant)
    print(
        f"{applications} application(s) from {len(apps)} published recipe(s), "
        f"{len(categories)} categories, {len(tags)} tags "
        f"({withheld} recipe(s) withheld as unpublished)"
    )
    print(f"Site written to {output_dir}")
    return len(apps)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        required=True,
        help="the catalog checkout's apps/ directory",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="output directory (replaced)"
    )
    args = parser.parse_args()

    try:
        build(args.catalog.resolve(), args.out.resolve())
    except SystemExit as e:
        print(e, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
