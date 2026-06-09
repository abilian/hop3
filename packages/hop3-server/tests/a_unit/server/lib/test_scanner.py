# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for hop3.server.lib.scanner (recursive package import scanning)."""

from __future__ import annotations

import sys

import pytest

from hop3.server.lib.scanner import (
    _iter_module_names,
    scan_package,
    scan_packages,
)


def test_scan_packages_rejects_a_bare_string():
    # A bare str is iterable char-by-char — guard against that easy mistake.
    with pytest.raises(AssertionError):
        scan_packages("json")


def test_scan_package_rejects_non_string():
    with pytest.raises(AssertionError):
        scan_package(["json"])  # ty: ignore[invalid-argument-type]


def test_iter_module_names_yields_submodules_of_a_package():
    names = set(_iter_module_names("json"))
    assert "json.decoder" in names
    assert "json.encoder" in names


def test_iter_module_names_is_empty_for_a_module():
    # A module (not a package) has no __path__ -> nothing to walk.
    assert list(_iter_module_names("json.decoder")) == []


def test_scan_package_imports_submodules_for_side_effects():
    sys.modules.pop("json.tool", None)
    scan_package("json")
    assert "json.tool" in sys.modules


def test_scan_packages_scans_each_package(monkeypatch):
    scanned: list[str] = []
    monkeypatch.setattr("hop3.server.lib.scanner.scan_package", scanned.append)
    scan_packages(["a.b", "c.d"])
    assert scanned == ["a.b", "c.d"]
