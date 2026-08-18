# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Maturity and build technology are orthogonal ways to select apps.

`make test-nix` used to mean `$(CATALOG_APPS)/beta`, on the reasoning that the
catalog's beta tier "is exactly the Nix-built variants". That was true only of
the initial seeding — native recipes landed in `golden`, Nix ones in `beta` —
and it had already stopped being true: 28 Nix recipes sat in `alpha` and 6 in
`broken`, so the Nix gate silently skipped half its subject. Promote one Nix app
to `golden` and the folder stops describing the technology at all.

So status selects a *directory* (ADR 059: the folder is the status) and
technology filters on the recipe's own `covers` tags. Neither stands in for the
other.
"""

from __future__ import annotations

import pytest
from hop3_testing.catalog.scanner import CATALOG_STATUSES, catalog_status_paths
from hop3_testing.cli.commands.test import _resolve_tests


@pytest.fixture
def repo_and_catalog(tmp_path):
    """A repo root with a sibling catalog checkout, as `hop3-test` expects."""
    root = tmp_path / "hop3"
    root.mkdir()
    apps = tmp_path / "hop3-catalog" / "apps"
    for status in CATALOG_STATUSES:
        (apps / status).mkdir(parents=True)
    return root, apps


def test_a_status_resolves_to_its_directory(repo_and_catalog):
    root, apps = repo_and_catalog

    assert catalog_status_paths(root, ["beta"]) == [str(apps / "beta")]


def test_statuses_compose_and_keep_their_order(repo_and_catalog):
    root, apps = repo_and_catalog

    assert catalog_status_paths(root, ["golden", "beta"]) == [
        str(apps / "golden"),
        str(apps / "beta"),
    ]


def test_alpha_is_reachable_though_it_is_not_in_the_default_scan_set(repo_and_catalog):
    """
    The reason status is a path and not a filter.

    `default_scan_paths` only walks golden+beta, so a filter-based `--status
    alpha` would have matched nothing and reported a clean run over 0 apps.
    """
    root, apps = repo_and_catalog

    assert catalog_status_paths(root, ["alpha"]) == [str(apps / "alpha")]


def test_status_and_paths_union_rather_than_conflict(repo_and_catalog):
    """
    Both name directories, so both can be asked for at once.

    `make test-nix` wants the publishable tiers *and* this repo's Nix fixtures;
    making the two spellings mutually exclusive would have forced it back to
    hardcoding `apps/beta` — the thing being removed.
    """
    root, _apps = repo_and_catalog

    # No recipes in the tmp catalog, so this asserts the resolution path runs
    # over the union without raising, not the count.
    assert (
        _resolve_tests(
            ("apps/test-apps-nix",),
            root,
            "dev",
            "docker",
            statuses=("golden", "beta"),
        )
        == []
    )


def test_a_misspelled_status_is_refused(repo_and_catalog):
    root, _ = repo_and_catalog

    with pytest.raises(ValueError, match="Unknown catalog status: gold"):
        catalog_status_paths(root, ["gold"])


def test_a_missing_catalog_checkout_is_refused(tmp_path):
    """Not "0 tests, all green" — the checkout is missing and must say so."""
    root = tmp_path / "hop3"
    root.mkdir()

    with pytest.raises(ValueError, match="No catalog checkout"):
        catalog_status_paths(root, ["golden"])


def test_a_status_the_catalog_lacks_is_refused(repo_and_catalog):
    root, apps = repo_and_catalog
    (apps / "retired").rmdir()

    with pytest.raises(ValueError, match="no retired directory"):
        catalog_status_paths(root, ["retired"])
