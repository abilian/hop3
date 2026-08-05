# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Presentation gate for catalog entries, run before publishing.

Every existing catalog check asks whether an app *works*: it deploys, it serves,
someone can sign in. None asks whether its entry is worth showing to anyone, and
the answer went unexamined for months — all 55 published entries rendered with
no tags, no memory, no services, no icon and a single category between them,
and fifteen had no ``[metadata]`` at all, so the catalog advertised an
application called ``Bookstack-Nix`` with no version and no description.

Each rule below exists because that specific thing shipped broken. The gate runs
at publish time rather than on the working tree, because installing from the
catalog reads the *published* artefact: a fix in ``apps/`` that has not been
published is not under test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.server.catalog.loader import find_icon, find_screenshots, load_apps
from hop3.server.catalog.taxonomy import CATEGORY_MAPPING

if TYPE_CHECKING:
    from hop3.server.catalog.models import CatalogApp

#: A catalog with no category is a catalog nobody can browse, and `Other` is
#: what the tag mapping returns when it recognises nothing — a default, not a
#: decision.
UNCATEGORIZED = "Other"


@dataclass(frozen=True)
class Violation:
    """One rule broken by one app."""

    app_id: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.app_id}: {self.rule} — {self.detail}"


def lint_app(app: CatalogApp) -> list[Violation]:
    """Check one loaded catalog entry. Returns every violation, not the first."""
    violations: list[Violation] = []

    def fail(rule: str, detail: str) -> None:
        violations.append(Violation(app.id, rule, detail))

    # The entry must describe itself. `title` falling back to the directory
    # name is what published `Bookstack-Nix`: the loader synthesises a title
    # when `[metadata]` is missing, so an entry looks fine until you read it.
    if not app.title:
        fail("no title", "the entry has no [metadata].title")
    if not app.description:
        fail("no description", "the entry has no [metadata].description")
    if not app.version:
        fail("no version", "the entry has no [metadata].version")

    if not app.category:
        fail("no category", "declare [catalog].category in catalog.toml")
    elif app.category == UNCATEGORIZED:
        known = ", ".join(sorted(CATEGORY_MAPPING))
        fail(
            "uncategorized",
            f"'{UNCATEGORIZED}' is not a category; pick one of: {known}",
        )

    if not app.tags:
        fail("no tags", "declare [catalog].tags in catalog.toml")

    if not app.memory:
        fail("no memory estimate", 'declare [catalog].memory (e.g. "512MB")')

    if not find_icon(app):
        fail("no icon", "add icon.webp or icon.png to the app directory")

    if not find_screenshots(app):
        fail(
            "no screenshots",
            "add captures under screenshots/ (they are discovered, not declared)",
        )

    return violations


def lint_catalog(apps_dir: Path) -> list[Violation]:
    """Check every entry under ``apps_dir``, in id order."""
    apps = load_apps(apps_dir)
    if not apps:
        msg = f"no catalog apps under {apps_dir}"
        raise ValueError(msg)

    violations: list[Violation] = []

    # Two entries claiming one id is not a display problem: the service keys
    # apps by id, so the second silently replaces the first and an application
    # disappears from the catalog with nothing logged.
    seen: dict[str, str] = {}
    for app in sorted(apps, key=lambda a: a.source_path):
        first = seen.get(app.id)
        if first is not None:
            violations.append(
                Violation(
                    app.id,
                    "duplicate id",
                    f"declared by both {first} and {Path(app.source_path).name}; "
                    "one of them will vanish from the catalog",
                )
            )
        else:
            seen[app.id] = Path(app.source_path).name

    for app in sorted(apps, key=lambda a: a.id):
        violations.extend(lint_app(app))
    return violations
