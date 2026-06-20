# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""A profile's selection rules resolve to a concrete test set (reusing Selector).

Real-catalog assertions (scans the repo's apps/ tree), like test_catalog.
"""

from __future__ import annotations

from hop3_testing.targets.helpers import find_project_root

from hop3_testlab.catalog import build_catalog
from hop3_testlab.discriminators import type_of
from hop3_testlab.selection import resolve_selection


def test_named_mode_preset_is_a_subset_of_full():
    catalog = build_catalog(find_project_root())
    smoke = resolve_selection(catalog, {"mode": "smoke"})
    full = resolve_selection(catalog, {"mode": "full"})
    assert smoke  # a named preset selects something
    assert set(smoke) <= set(full)  # smoke ⊆ full


def test_type_rule_selects_only_that_type():
    catalog = build_catalog(find_project_root())
    demos = resolve_selection(catalog, {"types": ["demo"]})
    assert demos
    assert all(n.startswith("demos/") for n in demos)  # demos only, no apps/tutos


def test_priority_and_type_rules_and_together():
    catalog = build_catalog(find_project_root())
    p0_apps = resolve_selection(catalog, {"priorities": ["P0"], "types": ["app"]})
    assert p0_apps
    assert all(type_of(n) == "app" for n in p0_apps)


def test_empty_selection_is_everything_runnable():
    catalog = build_catalog(find_project_root())
    everything = resolve_selection(catalog, {})
    full = resolve_selection(catalog, {"mode": "full"})
    # A bare profile (docker targets, no other constraint) ≈ the full docker suite.
    assert everything
    assert set(resolve_selection(catalog, {"types": ["demo"]})) <= set(everything)
    assert len(everything) >= len(full) // 2  # sanity: it's a broad set
