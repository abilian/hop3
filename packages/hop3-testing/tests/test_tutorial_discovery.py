# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tests for tutorial discovery (ADR 043 Phase 3).

Literate tutorials (``docs/src/tutorials/<lang>/<framework>.md``) are absorbed
into the unified catalog as ``type=tutorial`` entries that dispatch to the
validoc-driven TutorialTestRunner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.catalog.loader import generate_tutorial_test_definition
from hop3_testing.catalog.models import Priority, Tier
from hop3_testing.catalog.scanner import Catalog

if TYPE_CHECKING:
    from pathlib import Path


def _write_tutorial(root: Path, lang: str, framework: str, title: str) -> Path:
    d = root / "docs" / "src" / "tutorials" / lang
    d.mkdir(parents=True, exist_ok=True)
    md = d / f"{framework}.md"
    md.write_text(f"# {title}\n\nDeploy a {framework} app.\n")
    return md


def test_generate_tutorial_test_definition_basics(tmp_path: Path):
    md = _write_tutorial(tmp_path, "python", "flask", "Deploy Flask")

    td = generate_tutorial_test_definition(md)

    assert td.tutorial is not None
    assert td.tutorial.path == "flask.md"
    assert td.tutorial.runner == "validoc"
    assert td.runner_type == "tutorial"
    # P1 + slow so the nightly matrix (P0+P1) runs tutorials, not just `release`.
    assert td.priority == Priority.P1
    assert td.tier == Tier.SLOW
    assert td.demo is None
    assert td.deployment is None
    assert td.metadata.language == "python"
    assert td.metadata.framework == "flask"
    assert {"python", "flask"} <= set(td.metadata.covers)
    assert td.description == "Deploy Flask"
    # source_path drives the validoc runner: source_path.parent / tutorial.path
    assert td.source_path == md
    assert td.source_path.parent / td.tutorial.path == md


def test_catalog_discovers_tutorials(tmp_path: Path):
    _write_tutorial(tmp_path, "python", "flask", "Flask")
    _write_tutorial(tmp_path, "go", "gin", "Gin")
    _write_tutorial(tmp_path, "python", "django", "Django")
    # index.md / README.md must be ignored, not treated as tutorials.
    (tmp_path / "docs/src/tutorials/index.md").write_text("# Tutorials\n")

    catalog = Catalog(root=tmp_path)
    catalog.scan(paths=["docs/src/tutorials"])

    tutorials = [t for t in catalog if t.runner_type == "tutorial"]
    names = {t.name for t in tutorials}

    assert len(tutorials) == 3
    # Same-directory tutorials get distinct names (the file, not the dir).
    assert names == {
        "docs/src/tutorials/python/flask.md",
        "docs/src/tutorials/python/django.md",
        "docs/src/tutorials/go/gin.md",
    }
    assert not catalog.errors()


def test_catalog_skips_index_and_readme(tmp_path: Path):
    _write_tutorial(tmp_path, "python", "flask", "Flask")
    (tmp_path / "docs/src/tutorials/index.md").write_text("# Index\n")
    (tmp_path / "docs/src/tutorials/python/README.md").write_text("# Readme\n")

    catalog = Catalog(root=tmp_path)
    catalog.scan(paths=["docs/src/tutorials"])

    names = {t.name for t in catalog}
    assert names == {"docs/src/tutorials/python/flask.md"}
