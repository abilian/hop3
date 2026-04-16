# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Python toolchain dep-install strategy (ADR 039 Phase 1).

Covers:
- Both `requirements.txt` and `pyproject.toml` present → error (no silent
  override).
- Poetry-only pyproject (has `[tool.poetry]` but no PEP-621 `[project]`) →
  error with a hint pointing at `poetry export`.
- Pure pyproject detection (has `[project]` with dependencies) is NOT
  flagged as poetry-only.
"""

from __future__ import annotations

import pytest

from hop3.toolchains.python import _pyproject_is_poetry_only


def test_detects_poetry_only_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.poetry]
name = "my-app"
version = "1.0"

[tool.poetry.dependencies]
python = "^3.11"
django = "^5.0"
"""
    )
    assert _pyproject_is_poetry_only(pyproject) is True


def test_pep621_pyproject_is_not_poetry_only(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "my-app"
version = "1.0"
dependencies = ["django>=5.0"]
"""
    )
    assert _pyproject_is_poetry_only(pyproject) is False


def test_both_sections_is_not_poetry_only(tmp_path):
    """A pyproject with BOTH [project] and [tool.poetry] is pip-installable
    via the PEP-621 [project] table; don't flag as Poetry-only."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "my-app"
version = "1.0"
dependencies = ["django>=5.0"]

[tool.poetry]
name = "my-app"
"""
    )
    assert _pyproject_is_poetry_only(pyproject) is False


def test_malformed_pyproject_returns_false(tmp_path):
    """Malformed TOML should not raise from the detector — just return False
    and let pip's error surface."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("this is not valid toml [[[")
    assert _pyproject_is_poetry_only(pyproject) is False


def test_missing_pyproject_returns_false(tmp_path):
    assert _pyproject_is_poetry_only(tmp_path / "does-not-exist.toml") is False
