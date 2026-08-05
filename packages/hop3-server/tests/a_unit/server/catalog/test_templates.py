# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The dashboard's catalog templates must only read fields the model has.

Jinja renders an unknown attribute as the empty string and Alpine renders an
unknown key as ``undefined``, so a template can name a field that has never
existed and the page still returns 200. Three did: ``initials_bg_color`` (the
model calls it ``fallback_color``), ``long_description`` and ``min_memory``.
Every app card drew its fallback icon on a transparent background, and the
detail page's memory row never appeared.

The tier vocabulary had the same shape of bug: templates compared against
``lightweight``/``moderate`` while ``compute_resource_tier`` returns
``light``/``medium``, so every app was styled as ``heavy`` and the tier filter
matched nothing. That one is checked by :func:`test_tier_values_exist`.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest
from jinja2 import Environment, nodes

from hop3.server.catalog.models import CatalogApp

TEMPLATES = sorted(
    (Path(__file__).parents[4] / "src/hop3/server/templates/dashboard/catalog").glob(
        "*.html"
    )
)

#: Attributes a template may read: the dataclass fields plus the properties.
KNOWN_ATTRIBUTES = {f.name for f in fields(CatalogApp)} | {
    name
    for name, value in vars(CatalogApp).items()
    if isinstance(value, property) or callable(value)
}

#: Keys the JSON handed to Alpine actually carries.
SERIALIZED_KEYS = set(
    CatalogApp(
        id="x", title="X", description="", version="", author="", website="", license=""
    )
    .to_dict()
    .keys()
)

#: Alpine reads `app.foo` from JS inside these attributes, which Jinja never
#: parses — the `initials_bg_color` bug survived there longest.
_ALPINE_ATTR = re.compile(r'(?:x-[\w:.-]+|:[\w-]+|@[\w.-]+)="([^"]*)"')
_APP_FIELD = re.compile(r"\bapp\.(\w+)")


def _jinja_attributes(source: str) -> set[str]:
    """Every ``app.foo`` the Jinja compiler itself sees."""
    ast = Environment(autoescape=True).parse(source)
    return {
        node.attr
        for node in ast.find_all(nodes.Getattr)
        if isinstance(node.node, nodes.Name) and node.node.name == "app"
    }


def _alpine_attributes(source: str) -> set[str]:
    """Every ``app.foo`` in an Alpine expression."""
    return {
        match.group(1)
        for expr in _ALPINE_ATTR.findall(source)
        for match in _APP_FIELD.finditer(expr)
    }


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_jinja_only_reads_fields_the_model_has(template):
    unknown = _jinja_attributes(template.read_text()) - KNOWN_ATTRIBUTES

    assert not unknown, f"{template.name} reads non-existent CatalogApp {unknown}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_alpine_only_reads_keys_the_json_has(template):
    """Client-side rendering sees `to_dict()`, not the model."""
    unknown = _alpine_attributes(template.read_text()) - SERIALIZED_KEYS

    assert not unknown, f"{template.name} reads non-serialized {unknown} from JSON"


def test_the_templates_were_found():
    """A glob that matches nothing would pass every test above."""
    assert len(TEMPLATES) >= 5


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_tier_values_exist(template):
    """
    A tier a template compares against must be one the model can produce.

    Comparing to a value that never occurs is invisible: the badge just always
    takes the `else` branch, and the filter silently returns nothing.
    """
    produced = {
        CatalogApp(
            id="x",
            title="X",
            description="",
            version="",
            author="",
            website="",
            license="",
            memory=memory,
        ).compute_resource_tier()
        for memory in (None, "128MB", "512MB", "4GB")
    }

    source = template.read_text()
    compared = set(re.findall(r"resource_tier\s*==+\s*'(\w+)'", source))
    compared |= set(re.findall(r'<option value="(\w+)">', source)) - {"all"}

    assert compared <= produced, (
        f"{template.name} compares against {compared - produced}"
    )
