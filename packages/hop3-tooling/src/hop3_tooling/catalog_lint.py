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
from hop3.server.catalog.policy import PUBLISHABLE_STATUSES
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


def published_apps(apps_dir: Path) -> list[CatalogApp]:
    """The entries the catalog actually offers (ADR 059)."""
    return [a for a in load_apps(apps_dir) if a.status in PUBLISHABLE_STATUSES]


def lint_catalog(apps_dir: Path) -> list[Violation]:
    """
    Check every *published* entry under ``apps_dir``, in id order.

    Every rule here asks whether an entry is fit to show an operator, so it
    applies to the entries an operator is shown. A recipe kept at ``alpha`` or
    ``broken`` (ADR 059) is in the repository as a record, not an offer: it has
    no icon, no screenshot and no curated description because nobody is being
    invited to install it. Holding those to a presentation bar would make the
    only way to satisfy the lint deleting them.
    """
    # Two different failures, and telling them apart is the whole value of the
    # message: an empty tree is a wrong path or a broken checkout, while a tree
    # of recipes with nothing publishable is a real state of the catalog — and
    # one that must still fail, because signing an empty catalog would unpublish
    # every app on every node.
    all_apps = load_apps(apps_dir)
    if not all_apps:
        msg = f"no catalog apps under {apps_dir}"
        raise ValueError(msg)

    apps = [a for a in all_apps if a.status in PUBLISHABLE_STATUSES]
    if not apps:
        statuses = ", ".join(sorted({a.status for a in all_apps}))
        msg = (
            f"no published catalog apps under {apps_dir}: all {len(all_apps)} "
            f"recipe(s) are at a status the catalog does not publish ({statuses}). "
            f"Promote at least one, or this would sign an empty catalog."
        )
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
