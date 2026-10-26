# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Root pytest conftest.

Three responsibilities, all cross-package:

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

3. **Nothing in the workspace is optional.** ``pytest.importorskip`` fails
   instead of skipping, because a skipped import here is a test file that
   silently left a green run (``_import_or_fail``). Skips for a resource the
   harness cannot provision (``systemctl`` on macOS, a MySQL server) stay
   skips, and ``-ra`` prints each one's reason.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

# Env vars that name a REMOTE deploy/test target. They must never select or
# point a pytest target (see module docstring). Stripped session-wide so no
# test, fixture, or subprocess can inherit them. Remote is opt-in only via
# ``--ssh-host``. (Distinct from HOP3_HOST — the server's bind address — and
# HOP3_SSH_USER, which are left untouched.)
_TABOO_REMOTE_TARGET_VARS = (
    "HOP3_DEV_HOST",
    "HOP3_TEST_HOST",
    "HOP3_TEST_SERVER",
    # Cloud credentials and the server they point at. With these ambient, a
    # unit test that walked the deployer's --provider path rebuilt the
    # developer's dev server (Hetzner 115746898) on every run of the installer
    # suite for a month (2026-08-13 to 2026-09-09) and passed. No pytest layer
    # may hold a token that can rebuild a machine; provisioning is a CLI
    # operation (hop3-test run / hop3-deploy-server --provider), never a test.
    "HETZNER_API_TOKEN",
    "HCLOUD_TOKEN",
    "HETZNER_SERVER_ID",
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


_real_importorskip = pytest.importorskip
_session_patch = pytest.MonkeyPatch()


def pytest_configure(config: pytest.Config) -> None:
    """Make the remote-target env vars taboo; make every import mandatory."""
    for var in _TABOO_REMOTE_TARGET_VARS:
        os.environ.pop(var, None)
    _session_patch.setattr(pytest, "importorskip", _import_or_fail)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Hand pytest its own ``importorskip`` back."""
    _session_patch.undo()


def _import_or_fail(
    modname: str, minversion: str | None = None, reason: str | None = None
) -> ModuleType:
    """
    ``pytest.importorskip`` for workspace runs: a missing module fails.

    Inside the workspace every package and every extra is installed (the dev
    group pulls in ``hop3-server[waf]``), so a module-level ``importorskip``
    that fires is a venv synced some other way, and a whole test file vanished
    from a green run. That happened to the WAF suites. A package tested on its
    own has its own pytest rootdir and never loads this file, so the CLI's
    tests can still skip where hop3-server legitimately is not installed.
    """
    try:
        return _real_importorskip(modname, minversion, reason)
    except pytest.skip.Exception as exc:
        why = str(exc)
    pytest.fail(
        f"{modname} is missing from the workspace venv ({why}). "
        "Run `make develop`; plain `uv sync --no-dev` drops it.",
        pytrace=False,
    )


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
def repo_root() -> Path:
    """This checkout's root, where `demos/` and `apps/` live."""
    return Path(__file__).resolve().parent


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
