# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Resolve a profile's selection *rules* to a concrete set of test names.

A profile picks apps/demos/tutorials by rules, never a hand-picked list (v2 spec
§5). The rules reuse the engine's `Selector`/`ModeConfig` — a named-mode preset,
or tier/priority/target/tags filters, plus `representative` set-cover — and add
path-derived `type`/`variant` post-filters (the testlab discriminators) that the
engine's filter doesn't expose. Resolution runs against the *fetched* `source@ref`
catalog, so a profile yields exactly that ref's matching tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.selector.modes import ModeConfig, get_mode_config
from hop3_testing.selector.selector import Selector

from hop3_testlab.discriminators import type_of, variant_of

if TYPE_CHECKING:
    from hop3_testing.catalog import Catalog


def to_mode_config(selection: dict) -> ModeConfig:
    """Build a `ModeConfig` from a profile's selection rules.

    A named ``mode`` preset wins; otherwise the explicit tier/priority/target
    filters (an empty list = no constraint on that dimension). ``targets``
    defaults to ``docker`` so a bare profile doesn't pull in remote-only tests.
    """
    mode = selection.get("mode")
    if mode:
        return get_mode_config(mode)
    return ModeConfig(
        name="profile",
        tiers=list(selection.get("tiers", [])),
        priorities=list(selection.get("priorities", [])),
        targets=list(selection.get("targets", [])) or ["docker"],
        representative=bool(selection.get("representative")),
    )


def resolve_selection(catalog: Catalog, selection: dict) -> list[str]:
    """Concrete, sorted test names a profile's rules select from ``catalog``.

    ``type``/``variant`` post-filters narrow the engine's result; note that
    combining them with ``representative`` narrows the set-cover (a documented
    edge — profiles usually use one or the other).
    """
    config = to_mode_config(selection)
    tests = Selector(catalog).select(config, tags=selection.get("tags") or None)

    types = selection.get("types")
    if types:
        tests = [t for t in tests if type_of(t.name) in types]
    variants = selection.get("variants")
    if variants:
        tests = [t for t in tests if variant_of(t.name) in variants]
    return sorted(t.name for t in tests)
