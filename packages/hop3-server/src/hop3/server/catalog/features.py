# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Server features a catalog recipe can depend on.

The publisher runs each rule over a recipe's parsed ``hop3.toml`` and writes the
names it matches into the recipe's index entry (``requires``); a server refuses
to install an entry naming a feature it does not have. A feature is named rather
than versioned so the check holds for a development build or a backport, and the
refusal says what is missing. ``since`` gives the release that introduced it, for
servers that only read ``requires_hop3``.

A feature belongs here when a recipe that uses it fails on a server without it.
Add one in the release that introduces it; never rename or remove one, since
published catalogs name them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .policy import release_number

Recipe = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    since: str
    used_by: Callable[[Recipe], bool]


def _section(recipe: Recipe, name: str) -> Mapping[str, Any]:
    return recipe.get(name) or {}


def _php_fpm(recipe: Recipe) -> bool:
    build, run = _section(recipe, "build"), _section(recipe, "run")
    return build.get("toolchain") == "php" and not run.get("start")


#: nix-gen templates that can build from the app's own directory: these with
#: the flag that asks for it, and the rest whenever the recipe names no source.
#: ``test_features.py`` checks this against the templates themselves.
LOCAL_SOURCE_FLAGS = {
    "python-venv": "pip-local-source",
    "node-pnpm-install": "node-local-source",
}
SOURCELESS_IS_LOCAL = frozenset({"go-source", "php-app", "ruby-bundler"})


def _nix_local_source(recipe: Recipe) -> bool:
    nix = _section(recipe, "nix")
    template = nix.get("template")
    if template in LOCAL_SOURCE_FLAGS:
        return bool(nix.get(LOCAL_SOURCE_FLAGS[template]))
    return template in SOURCELESS_IS_LOCAL and not {"url", "github"} & set(nix)


FEATURES: tuple[Feature, ...] = (
    Feature(
        "admin-verify",
        "0.7.3",
        lambda r: "verify" in _section(r, "admin") or "verify" in _section(r, "probe"),
    ),
    Feature(
        "proxy-limits",
        "0.7.4",
        lambda r: bool(
            {"max-body-size", "request-buffering"} & set(_section(r, "proxy"))
        ),
    ),
    Feature("php-fpm", "0.7.5", _php_fpm),
    Feature(
        "document-root", "0.7.5", lambda r: "document-root" in _section(r, "build")
    ),
    Feature("proxy-deny", "0.8", lambda r: "deny" in _section(r, "proxy")),
    Feature("access-gate", "0.8", lambda r: "access" in r),
    Feature(
        "scratch-volumes",
        "0.8",
        lambda r: any(v.get("type") == "scratch" for v in r.get("volumes") or ()),
    ),
    Feature("nix-github-source", "0.8", lambda r: "github" in _section(r, "nix")),
    Feature("nix-local-source", "0.8", _nix_local_source),
    Feature(
        "nix-gem-cargo-hashes",
        "0.8",
        lambda r: "gem-cargo-hashes" in _section(r, "nix"),
    ),
)

SERVER_FEATURES: frozenset[str] = frozenset(f.name for f in FEATURES)


def features_used(recipe: Recipe) -> list[Feature]:
    """The features a recipe uses, in table order."""
    return [f for f in FEATURES if f.used_by(recipe)]


def release_needed(features: list[Feature]) -> str:
    """The lowest release that has every one of ``features``, or ``""``."""
    return max((f.since for f in features), key=release_number, default="")
