# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Every committed nix-gen recipe must still generate a valid expression.

The per-template tests pin behaviour against synthetic specs; this pins it
against the recipes we actually ship: this repo's fixtures and demos on every
run, and the catalog's with ``--catalog`` (``make test-catalog``). It is the half of the reproducibility gate
that needs no Nix daemon and no server, so it runs on every push, while
``make gate-nix`` (rebuild + deploy) runs where a warm store exists.

What it catches: a recipe referencing a spec field a template dropped, a
lockfile that was never committed, a generated expression that no longer parses
as Nix.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import tomllib

from hop3.plugins.build.nix.gen.registry import generate, get_template
from hop3.plugins.build.nix.gen.templates.base import ejected
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config

if TYPE_CHECKING:
    from pathlib import Path

# apps/test-apps-nix holds hand-written hop3.nix files, which this test has
# nothing to say about; apps/test-apps-nix-gen holds the small templated
# fixtures that mirror them. The demos deploy through the same templates
# (demo22 kept a retired key). Globs from the repo root.
REPO_RECIPES = ("apps/test-apps-nix-gen/*/hop3.toml", "demos/demo*/app/hop3.toml")
#: The catalog's, from its apps/; checked only with --catalog.
CATALOG_RECIPES = ("beta/*/hop3.toml", "alpha/*/hop3.toml")


def _nix_gen_dirs(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    return sorted(
        toml_file.parent
        for pattern in patterns
        for toml_file in root.glob(pattern)
        if "template" in (tomllib.loads(toml_file.read_text()).get("nix") or {})
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """
    One ``recipe`` per nix-gen recipe: this repo's, and the catalog's with
    ``--catalog``. Found here rather than at import, where neither the repo
    root nor the option is known.
    """
    if "recipe" not in metafunc.fixturenames:
        return
    root = metafunc.config.rootpath
    params = [
        pytest.param(d, id=str(d.relative_to(root)))
        for d in _nix_gen_dirs(root, REPO_RECIPES)
    ]
    if (catalog := metafunc.config.getoption("--catalog")) is not None:
        apps = catalog.resolve() / "apps"
        params += [
            pytest.param(
                d, id=f"catalog/{d.relative_to(apps)}", marks=pytest.mark.catalog
            )
            for d in _nix_gen_dirs(apps, CATALOG_RECIPES)
        ]
    metafunc.parametrize("recipe", params, scope="module")


def test_the_corpus_is_not_empty(pytestconfig):
    """A sweep that found nothing to sweep must not report success."""
    root = pytestconfig.rootpath
    assert _nix_gen_dirs(root, REPO_RECIPES), f"no nix-gen recipe for {REPO_RECIPES}"


@pytest.fixture(scope="module")
def expression(recipe: Path) -> tuple[Path, str]:
    config = tomllib.loads((recipe / "hop3.toml").read_text())
    spec = app_spec_from_config(
        config["nix"], config.get("metadata") or {}, recipe.name
    )
    return recipe, generate(spec)


def test_recipe_generates(expression):
    app_dir, output = expression
    assert output.startswith("# hop3.nix"), app_dir.name
    assert "pkgs ? import (fetchTarball" in output, (
        f"{app_dir.name}: nixpkgs not pinned"
    )


def test_recipe_can_be_ejected(expression):
    """`hop3 nix eject` rewrites both header lines, whatever the template."""
    app_dir, output = expression
    config = tomllib.loads((app_dir / "hop3.toml").read_text())
    template = config["nix"]["template"]
    result = ejected(output, template, "2026-01-01")
    assert "GENERATED" not in result, app_dir.name
    assert "nix eject" not in result, app_dir.name
    assert f"# Ejected from template '{template}' on 2026-01-01." in result


def test_recipe_declares_a_reproducibility_tier(expression):
    """An app's published tier (ADR 008) is read off its template."""
    app_dir, _ = expression
    config = tomllib.loads((app_dir / "hop3.toml").read_text())
    assert get_template(config["nix"]["template"]).tier


@pytest.mark.skipif(
    shutil.which("nix-instantiate") is None, reason="needs Nix (runs in the NixOS CI)"
)
def test_generated_expression_parses_as_nix(expression, tmp_path):
    """String assertions can't tell a valid expression from a plausible one."""
    app_dir, output = expression
    nix_file = tmp_path / f"{app_dir.name}.nix"
    nix_file.write_text(output)
    result = subprocess.run(
        ["nix-instantiate", "--parse", str(nix_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{app_dir.name}:\n{result.stderr}"


# --- a static root served from the frontend derivation needs its source assets ---

STATIC_ROOT_MARKER = "$HOP3_GO_FRONTEND"


def test_a_go_static_root_also_ships_its_source_assets(catalog_apps):
    """
    gitea and forgejo are the same codebase and drifted apart.

    Both point STATIC_ROOT_PATH at the built frontend, and both also resolve
    `options/` (locales, licences, label templates) there. That directory is a
    *source* asset, so the frontend derivation does not contain it unless the
    recipe says so. Omitting it lets the app boot, serve nothing, and die
    registering a cron task — "translation is missing for task update_mirrors".
    gitea hit it; forgejo hit the identical failure weeks later.
    """
    serving = [
        d
        for d in _nix_gen_dirs(catalog_apps, CATALOG_RECIPES)
        if STATIC_ROOT_MARKER in (d / "hop3.toml").read_text()
    ]
    assert serving, "no recipe serves a Go static root — has the wiring changed?"
    missing = [
        d.name
        for d in serving
        if not (
            tomllib.loads((d / "hop3.toml").read_text())["nix"].get("go-static-dirs")
        )
    ]
    assert not missing, (
        f"{missing} serve a static root from the frontend derivation but ship no "
        "go-static-dirs; source assets under that root will be absent at runtime"
    )
