# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Every committed nix-gen recipe must still generate a valid expression.

The per-template tests pin behaviour against synthetic specs; this pins it
against the corpus we actually ship. It is the half of the reproducibility gate
that needs no Nix daemon and no server, so it runs on every push, while
``make gate-nix`` (rebuild + deploy) runs where a warm store exists.

What it catches: a recipe referencing a spec field a template dropped, a
lockfile that was never committed, a generated expression that no longer parses
as Nix.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import tomllib

from hop3.plugins.build.nix.gen.registry import generate, get_template
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config

# apps/test-apps-nix holds hand-written hop3.nix files, which this test has
# nothing to say about; apps/test-apps-nix-gen holds the small templated
# fixtures that mirror them.
CORPUS_ROOTS = (Path("apps/real-apps-nix-gen"), Path("apps/test-apps-nix-gen"))


def _recipes() -> list[Path]:
    return sorted(
        toml_file.parent
        for root in CORPUS_ROOTS
        for toml_file in root.glob("*/hop3.toml")
        if "template" in (tomllib.loads(toml_file.read_text()).get("nix") or {})
    )


RECIPES = _recipes()


def test_the_corpus_is_not_empty():
    """A sweep that found nothing to sweep must not report success."""
    assert RECIPES, f"no nix-gen recipe under {[str(r) for r in CORPUS_ROOTS]}"


@pytest.fixture(scope="module", params=RECIPES, ids=lambda p: p.name)
def expression(request) -> tuple[Path, str]:
    app_dir = request.param
    config = tomllib.loads((app_dir / "hop3.toml").read_text())
    spec = app_spec_from_config(
        config["nix"], config.get("metadata") or {}, app_dir.name
    )
    return app_dir, generate(spec)


def test_recipe_generates(expression):
    app_dir, output = expression
    assert output.startswith("# hop3.nix"), app_dir.name
    assert "pkgs ? import (fetchTarball" in output, (
        f"{app_dir.name}: nixpkgs not pinned"
    )


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
