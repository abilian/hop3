# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for catalog taxonomy: slugify and category/tag grouping.

Locks down the pure transforms that turn app tags into URL slugs and into
grouped/counted Category and Tag aggregates.
"""

from __future__ import annotations

from hop3.server.catalog.models import CatalogApp
from hop3.server.catalog.taxonomy import (
    build_categories,
    build_tags,
    get_category_for_app,
    slugify,
)


def make_app(title: str, tags: list[str] | None = None) -> CatalogApp:
    """Build a minimal CatalogApp with just a title and tags."""
    return CatalogApp(
        id=title.lower(),
        title=title,
        description="",
        version="1.0",
        author="",
        website="",
        license="",
        tags=tags or [],
    )


class TestSlugify:
    """slugify: lowercase, spaces -> '-', '&' -> 'and', drop apostrophes."""

    def test_lowercases_text(self) -> None:
        assert slugify("HELLO") == "hello"

    def test_replaces_spaces_with_hyphens(self) -> None:
        assert slugify("project management") == "project-management"

    def test_replaces_ampersand_with_and(self) -> None:
        assert slugify("Forms & Surveys") == "forms-and-surveys"

    def test_strips_apostrophes(self) -> None:
        assert slugify("Bob's Tools") == "bobs-tools"

    def test_empty_string_stays_empty(self) -> None:
        assert slugify("") == ""

    def test_combined_transforms(self) -> None:
        # All rules applied at once: case + space + ampersand + apostrophe.
        assert slugify("Cats & Dog's Things") == "cats-and-dogs-things"

    def test_preserves_unicode_letters(self) -> None:
        # slugify only lowercases and substitutes a fixed set of chars; it
        # does not transliterate, so accented letters survive lowercased.
        assert slugify("Café Münch") == "café-münch"


class TestGetCategoryForApp:
    """get_category_for_app maps the first matching tag keyword to a category."""

    def test_matches_known_keyword(self) -> None:
        app = make_app("Nextcloud", tags=["storage"])
        assert get_category_for_app(app) == "File Storage"

    def test_keyword_match_is_case_insensitive(self) -> None:
        app = make_app("Nextcloud", tags=["STORAGE"])
        assert get_category_for_app(app) == "File Storage"

    def test_unknown_tags_fall_back_to_other(self) -> None:
        app = make_app("Mystery", tags=["unmapped-thing"])
        assert get_category_for_app(app) == "Other"

    def test_no_tags_falls_back_to_other(self) -> None:
        app = make_app("Bare", tags=[])
        assert get_category_for_app(app) == "Other"

    def test_first_category_in_mapping_order_wins(self) -> None:
        # "files" -> File Storage precedes "git" -> Development in the mapping,
        # so the category iteration order decides the winner, not tag order.
        app = make_app("Both", tags=["git", "files"])
        assert get_category_for_app(app) == "File Storage"


class TestBuildCategories:
    """build_categories groups apps, sets app.category, sorts and counts."""

    def test_groups_apps_into_their_categories(self) -> None:
        apps = [
            make_app("Drive", tags=["storage"]),
            make_app("Board", tags=["kanban"]),
        ]

        categories = build_categories(apps)

        by_name = {c.name: c for c in categories}
        assert {"File Storage", "Project Management"} == set(by_name)
        assert by_name["File Storage"].app_count == 1
        assert by_name["Project Management"].app_count == 1

    def test_sets_category_field_on_each_app(self) -> None:
        app = make_app("Drive", tags=["storage"])

        build_categories([app])

        assert app.category == "File Storage"

    def test_categories_ordered_by_descending_app_count(self) -> None:
        apps = [
            make_app("Drive", tags=["storage"]),
            make_app("Box", tags=["sync"]),
            make_app("Board", tags=["kanban"]),
        ]

        categories = build_categories(apps)

        # File Storage has 2 apps, Project Management has 1 -> File Storage first.
        assert categories[0].name == "File Storage"
        assert categories[0].app_count == 2

    def test_apps_within_category_sorted_by_title(self) -> None:
        apps = [
            make_app("Zebra", tags=["storage"]),
            make_app("alpha", tags=["storage"]),
        ]

        categories = build_categories(apps)

        titles = [a.title for a in categories[0].apps]
        assert titles == ["alpha", "Zebra"]

    def test_category_id_is_slug_with_and_substitution(self) -> None:
        app = make_app("Poll", tags=["forms"])

        categories = build_categories([app])

        assert categories[0].id == "forms-and-surveys"

    def test_category_carries_description_and_icon(self) -> None:
        app = make_app("Drive", tags=["storage"])

        category = build_categories([app])[0]

        assert category.description == "Store, sync, and share files securely"
        assert category.icon == "folder"

    def test_empty_app_list_yields_no_categories(self) -> None:
        assert build_categories([]) == []


class TestBuildTags:
    """build_tags groups apps by tag, sorts and counts."""

    def test_groups_apps_under_shared_tag(self) -> None:
        apps = [
            make_app("A", tags=["python"]),
            make_app("B", tags=["python"]),
        ]

        tags = build_tags(apps)

        assert len(tags) == 1
        assert tags[0].name == "python"
        assert tags[0].app_count == 2

    def test_distinct_tags_become_distinct_tag_objects(self) -> None:
        apps = [make_app("A", tags=["python", "flask"])]

        tags = build_tags(apps)

        assert {t.name for t in tags} == {"python", "flask"}

    def test_tags_ordered_by_descending_app_count(self) -> None:
        apps = [
            make_app("A", tags=["python", "rare"]),
            make_app("B", tags=["python"]),
        ]

        tags = build_tags(apps)

        assert tags[0].name == "python"
        assert tags[0].app_count == 2

    def test_apps_within_tag_sorted_by_title(self) -> None:
        apps = [
            make_app("Zeta", tags=["x"]),
            make_app("alpha", tags=["x"]),
        ]

        tags = build_tags(apps)

        assert [a.title for a in tags[0].apps] == ["alpha", "Zeta"]

    def test_tag_id_slugifies_spaces(self) -> None:
        app = make_app("A", tags=["no code"])

        tags = build_tags([app])

        assert tags[0].id == "no-code"

    def test_empty_app_list_yields_no_tags(self) -> None:
        assert build_tags([]) == []
