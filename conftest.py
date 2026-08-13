# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Root pytest conftest.

Two responsibilities, both cross-package:

1. **Tier markers from the directory layer (ADR 043).** The fast / integration
   / e2e split is encoded by where a test lives, not by hand-applied decorators
   (which drifted into being decorative). This makes `pytest -m fast` and
   `pytest -m "not needs_docker"` select the right lane in every package.

2. **Remote targets are opt-in, and only via an explicit flag (ADR 043 / 052).**
   e2e tests run against Docker by default. A remote host is selected ONLY by
   the explicit ``--ssh-host`` option, never by an ambient env var: a
   developer's ``HOP3_DEV_HOST`` / ``HOP3_TEST_HOST`` (set for
   ``hop3-deploy-server`` / ``hop3-test``) used to silently redirect e2e tests
   at a real box, colliding with live ``hop3-test`` runs. Those vars are now
   taboo for pytest — stripped for the whole session so nothing can read them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

# Env vars that name a REMOTE deploy/test target. They must never select or
# point a pytest target (see module docstring). Stripped session-wide so no
# test, fixture, or subprocess can inherit them. Remote is opt-in only via
# ``--ssh-host``. (Distinct from HOP3_HOST — the server's bind address — and
# HOP3_SSH_USER, which are left untouched.)
_TABOO_REMOTE_TARGET_VARS = (
    "HOP3_DEV_HOST",
    "HOP3_TEST_HOST",
    "HOP3_TEST_SERVER",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the one explicit remote-target opt-in, shared by all packages."""
    group = parser.getgroup("hop3", "Hop3 test options")
    group.addoption(
        "--ssh-host",
        action="store",
        default=None,
        metavar="HOST",
        help=(
            "Run e2e tests against this remote SSH host (explicit opt-in). "
            "Without it, e2e tests only ever touch Docker. HOP3_TEST_HOST / "
            "HOP3_DEV_HOST are deliberately ignored — an env var must never "
            "redirect a pytest run at a real box."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Make the remote-target env vars taboo for the whole pytest session."""
    for var in _TABOO_REMOTE_TARGET_VARS:
        os.environ.pop(var, None)


@pytest.fixture
def remote_ssh_host(request: pytest.FixtureRequest) -> str | None:
    """
    The explicit ``--ssh-host`` value, or None. The ONLY remote-target source.

    Tests that need a remote host must depend on this fixture (and skip when it
    is None). They must not read HOP3_TEST_HOST / HOP3_DEV_HOST.
    """
    return request.config.getoption("--ssh-host")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Tag each collected test with its tier marker, derived from its path.

    - ``c_e2e`` / ``c_system`` -> ``e2e`` + ``needs_docker`` (real deploy, Docker)
    - ``b_integration``        -> ``integration``           (in-process, real DB)
    - everything else          -> ``fast``                  (a_unit + flat unit)
    """
    for item in items:
        path = str(getattr(item, "path", "") or item.fspath)
        if "/c_e2e/" in path or "/c_system/" in path:
            item.add_marker("e2e")
            item.add_marker("needs_docker")
        elif "/b_integration/" in path:
            item.add_marker("integration")
        else:
            item.add_marker("fast")


@pytest.fixture(scope="session")
def catalog_apps() -> Path:
    """
    The sibling catalog checkout's ``apps/``.

    Corpus regressions read real recipes, and the recipes live in the catalog
    repository now. One fixture rather than a constant per test file: four of
    them had grown, each counting ``Path(__file__).parents[N]`` to a different
    depth, which is a fact about where a file sits rather than about the corpus.
    """
    return Path(__file__).resolve().parent.parent / "hop3-catalog" / "apps"


@pytest.fixture(scope="session")
def catalog_recipe(catalog_apps: Path) -> Callable[[str], Path]:
    """
    Resolve a recipe directory by app id, wherever its maturity has filed it.

    Globs rather than joins: a recipe moves between ``golden``, ``beta`` and
    ``alpha`` as it earns or loses a status (ADR 059), so its status directory
    is not knowable from its id and a joined path would break on promotion.
    """

    def resolve(app_id: str) -> Path:
        hits = sorted(catalog_apps.glob(f"*/{app_id}/hop3.toml"))
        assert hits, f"no catalog recipe for {app_id!r} under {catalog_apps}"
        return hits[0].parent

    return resolve
