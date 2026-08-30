# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Browsing the catalog shows applications; installing uses recipes.

One application may be packaged several ways — bookstack, bookstack-nix and
bookstack-nixgen install the same software by different routes — and the
catalog published all three as separate entries. An operator browsing saw three
cards for one application and no way to tell that the difference was a build
path rather than a product.
"""

from __future__ import annotations

import json

import pytest

from hop3.server.catalog.service import CatalogService


@pytest.fixture(autouse=True)
def _reset_singleton():
    CatalogService.reset()
    yield
    CatalogService.reset()


def _app(catalog_dir, app_id, *, variant_of="", build_path="native", featured=False):
    d = catalog_dir / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(
        f'[metadata]\nid = "{app_id}"\ntitle = "{app_id}"\n'
        f'description = "a thing"\ntags = ["shared"]\n'
    )
    overlay = "[catalog]\n"
    if variant_of:
        overlay += f'variant_of = "{variant_of}"\n'
    overlay += f'build_path = "{build_path}"\n'
    if featured:
        overlay += "featured = true\n"
    (d / "catalog.toml").write_text(overlay)


def _loaded(tmp_path, apps):
    cat = tmp_path / "catalog"
    for kwargs in apps:
        _app(cat, **kwargs)
    index = {
        "format": 1,
        "serial": 1,
        "apps": [
            {
                "id": a["app_id"],
                "files": [
                    {"path": f"{a['app_id']}/hop3.toml", "sha256": "0" * 64},
                    {"path": f"{a['app_id']}/catalog.toml", "sha256": "0" * 64},
                ],
            }
            for a in apps
        ],
    }
    (cat / "index.json").write_text(json.dumps(index))
    svc = CatalogService.get_instance()
    svc.load(cat)
    return svc


THREE_WAYS = [
    {"app_id": "bookstack"},
    {"app_id": "bookstack-nix", "variant_of": "bookstack", "build_path": "nix"},
    {"app_id": "bookstack-nixgen", "variant_of": "bookstack", "build_path": "nixgen"},
]


def test_browsing_shows_one_entry_per_application(tmp_path):
    svc = _loaded(tmp_path, THREE_WAYS)

    assert [a.id for a in svc.list_apps()] == ["bookstack"]


def test_every_recipe_is_still_enumerable(tmp_path):
    """The acceptance harness installs what the server publishes, all of it."""
    svc = _loaded(tmp_path, THREE_WAYS)

    assert len(svc.list_apps(include_variants=True)) == 3


def test_every_recipe_is_still_installable_by_id(tmp_path):
    """Folding a variant out of the listing must not make it unreachable."""
    svc = _loaded(tmp_path, THREE_WAYS)

    assert svc.get_app("bookstack-nixgen") is not None


def test_variants_are_offered_on_the_application(tmp_path):
    """The choice stays available, on the entry it belongs to."""
    svc = _loaded(tmp_path, THREE_WAYS)

    offered = svc.variants_of("bookstack")

    assert [a.id for a in offered] == [
        "bookstack",
        "bookstack-nix",
        "bookstack-nixgen",
    ]


def test_an_application_packaged_once_offers_no_choice(tmp_path):
    """No selector where there is nothing to select."""
    svc = _loaded(tmp_path, [{"app_id": "paheko"}])

    assert svc.variants_of("paheko") == []


def test_asking_a_variant_for_its_variants_yields_nothing(tmp_path):
    """The application owns the list, so it is asked for by the application."""
    svc = _loaded(tmp_path, THREE_WAYS)

    assert svc.variants_of("bookstack-nix") == []


def test_search_does_not_return_the_same_application_three_times(tmp_path):
    svc = _loaded(tmp_path, THREE_WAYS)

    assert [a.id for a in svc.search("bookstack")] == ["bookstack"]


def test_a_featured_variant_does_not_reach_the_featured_row(tmp_path):
    """Featured is a property of the application, not of a build path."""
    svc = _loaded(
        tmp_path,
        [
            {"app_id": "bookstack", "featured": True},
            {
                "app_id": "bookstack-nix",
                "variant_of": "bookstack",
                "build_path": "nix",
                "featured": True,
            },
        ],
    )

    assert [a.id for a in svc.get_featured_apps()] == ["bookstack"]


def test_categories_and_tags_count_applications(tmp_path):
    """A category saying "3 apps" for one application is a miscount."""
    svc = _loaded(tmp_path, THREE_WAYS)

    for category in svc.list_categories():
        assert [a.id for a in category.apps] == ["bookstack"]
    for tag in svc.list_tags():
        assert [a.id for a in tag.apps] == ["bookstack"]
