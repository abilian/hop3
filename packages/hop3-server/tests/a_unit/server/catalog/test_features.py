# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Server features a recipe needs: detection, publish check, index round-trip."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hop3.plugins.build.nix.gen import templates as nix_templates
from hop3.server.catalog.features import (
    LOCAL_SOURCE_FLAGS,
    SOURCELESS_IS_LOCAL,
    features_used,
    release_needed,
)
from hop3.server.catalog.loader import load_apps_from_index
from hop3.server.catalog.publish import PublishError, build_index

PHP_RECIPE = {"build": {"toolchain": "php"}, "run": {"before-run": "setup"}}


def _names(recipe):
    return [f.name for f in features_used(recipe)]


def test_a_php_recipe_without_a_start_command_needs_php_fpm():
    assert _names(PHP_RECIPE) == ["php-fpm"]
    assert _names({"build": {"toolchain": "php"}, "run": {"start": "php -S"}}) == []


def test_a_recipe_with_no_new_feature_requires_nothing():
    recipe = {"metadata": {"id": "x"}, "build": {"toolchain": "python"}}
    assert _names(recipe) == []
    assert release_needed(features_used(recipe)) == ""


def test_the_release_needed_is_the_highest_among_the_features():
    recipe = {**PHP_RECIPE, "proxy": {"deny": ["/data"], "max-body-size": "2G"}}
    assert _names(recipe) == ["proxy-limits", "php-fpm", "proxy-deny"]
    assert release_needed(features_used(recipe)) == "0.8"


def test_a_nixpkgs_wrapper_recipe_is_not_local_source():
    assert _names({"nix": {"template": "nixpkgs-wrapper"}}) == []
    assert _names({"nix": {"template": "go-source"}}) == ["nix-local-source"]
    assert _names({"nix": {"template": "go-source", "url": "https://x"}}) == []
    assert _names({"nix": {"template": "python-venv"}}) == []
    flagged = {"template": "python-venv", "pip-local-source": True}
    assert _names({"nix": flagged}) == ["nix-local-source"]


def _app(content, catalog_toml=None):
    app = content / "paheko"
    app.mkdir(parents=True)
    (app / "hop3.toml").write_text(
        '[metadata]\nid = "paheko"\n[build]\ntoolchain = "php"\n'
    )
    (app / "check.py").write_text("# smoke test\n")
    if catalog_toml is not None:
        (app / "catalog.toml").write_text(catalog_toml)
    return app


@pytest.mark.parametrize("declared", [None, '[catalog]\nrequires_hop3 = "0.7"\n'])
def test_publish_refuses_a_requires_hop3_below_what_the_recipe_uses(tmp_path, declared):
    _app(tmp_path, declared)
    with pytest.raises(PublishError, match=r'php-fpm \(0\.7\.5\).*"0\.7\.5"'):
        build_index(tmp_path, serial=1)


def test_publish_writes_requires_and_the_server_reads_it_back(tmp_path):
    _app(tmp_path, '[catalog]\nrequires_hop3 = "0.8"\n')  # higher is kept

    index = build_index(tmp_path, serial=1).index

    (entry,) = index["apps"]
    assert entry["requires"] == ["php-fpm"]
    (app,) = load_apps_from_index(tmp_path, json.loads(json.dumps(index)))
    assert app.requires == ["php-fpm"]
    assert app.requires_hop3 == "0.8"


def test_a_recipe_needing_no_feature_is_published_as_such(tmp_path):
    """
    An entry without `requires` reads as one published before feature names,
    so the server checked `requires_hop3` instead: a development build refused
    every such recipe declaring the next release.
    """
    app = tmp_path / "radicale"
    app.mkdir()
    (app / "hop3.toml").write_text(
        '[metadata]\nid = "radicale"\n[build]\ntoolchain = "python"\n'
    )
    (app / "check.py").write_text("# smoke test\n")

    index = build_index(tmp_path, serial=1).index

    (entry,) = index["apps"]
    assert entry["requires"] == []
    (loaded,) = load_apps_from_index(tmp_path, json.loads(json.dumps(index)))
    assert loaded.requires == []


def test_the_local_source_templates_are_the_ones_that_build_locally():
    """
    The rule names templates by hand. A template that learns to build from the
    app's own directory, and is missing here, makes the publisher miss the
    feature and an older server fail at build.
    """
    template_dir = Path(nix_templates.__file__).parent
    building_locally = set()
    for source in template_dir.glob("*.py"):
        text = source.read_text()
        name = re.search(r'^    name = "([a-z-]+)"$', text, re.MULTILINE)
        if name and "local_source_expr()" in text:
            building_locally.add(name.group(1))

    assert building_locally == SOURCELESS_IS_LOCAL | set(LOCAL_SOURCE_FLAGS)


def test_an_entry_whose_requires_is_not_a_list_of_names_is_left_out(tmp_path):
    """A string would read as one feature per character; the rest still loads."""
    _app(tmp_path, '[catalog]\nrequires_hop3 = "0.8"\n')
    index = build_index(tmp_path, serial=1).index
    index["apps"][0]["requires"] = "php-fpm"

    assert load_apps_from_index(tmp_path, index) == []
