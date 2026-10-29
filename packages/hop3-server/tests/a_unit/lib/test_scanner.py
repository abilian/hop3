# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for hop3.lib.scanner (recursive package import scanning)."""

from __future__ import annotations

import sys

from hop3.lib.scanner import _iter_module_names, scan_package


def test_iter_module_names_yields_submodules_of_a_package():
    names = set(_iter_module_names("json"))
    assert "json.decoder" in names
    assert "json.encoder" in names


def test_iter_module_names_is_empty_for_a_module():
    # A module (not a package) has no __path__ -> nothing to walk.
    assert list(_iter_module_names("json.decoder")) == []


def test_scan_package_imports_submodules_and_returns_them():
    sys.modules.pop("json.tool", None)
    modules = scan_package("json")
    assert "json.tool" in sys.modules
    assert sys.modules["json.tool"] in modules
