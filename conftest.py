# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root pytest conftest — stamp tier markers from the directory layer (ADR 043).

The fast / integration / e2e split is encoded by where a test lives, not by
hand-applied decorators (which drifted into being decorative). This hook makes
the markers load-bearing across *all* packages, so `pytest -m fast` and
`pytest -m "not needs_docker"` select the right lane no matter which package a
test is in:

- ``c_e2e`` / ``c_system`` -> ``e2e`` + ``needs_docker`` (real deploy, Docker)
- ``b_integration``        -> ``integration``           (in-process, real DB)
- everything else          -> ``fast``                  (a_unit + flat unit suites)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag each collected test with its tier marker, derived from its path."""
    for item in items:
        path = str(getattr(item, "path", "") or item.fspath)
        if "/c_e2e/" in path or "/c_system/" in path:
            item.add_marker("e2e")
            item.add_marker("needs_docker")
        elif "/b_integration/" in path:
            item.add_marker("integration")
        else:
            item.add_marker("fast")
