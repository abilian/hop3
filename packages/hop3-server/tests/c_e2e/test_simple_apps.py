# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests using the hop3-testing framework."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource
from hop3_testing.exceptions import DeploymentError

# Get all test apps from the platform fixture directories.
#
# These were `test-apps/` and `nix-apps/` until they were renamed. Nothing
# noticed, because a missing directory collected zero params and pytest
# reported "1 skipped" — so the repo's main e2e deploy test ran against
# nothing at all while looking green. `_collect_apps` now refuses a missing
# directory rather than quietly yielding an empty set.
APPS_ROOT = Path(__file__).parents[4] / "apps"
TEST_APPS_DIR = APPS_ROOT / "test-apps-procfile"
NIX_APPS_DIR = APPS_ROOT / "test-apps-nix"


def _collect_apps(app_dir: Path) -> list:
    """
    Collect test apps from a directory, which must exist and be non-empty.

    The `return []` this used to start with is what let a directory rename go
    unnoticed: the parametrize list went empty, pytest said "1 skipped", and
    the e2e deploy suite tested nothing for as long as nobody read the reason.
    A fixture directory that isn't there is a broken checkout, not zero apps.
    """
    if not app_dir.exists():
        msg = (
            f"e2e fixture directory {app_dir} does not exist. This suite "
            f"deploys the apps found there; with no directory it would collect "
            f"zero tests and report success without deploying anything."
        )
        raise RuntimeError(msg)
    apps = []
    for d in sorted(app_dir.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and not _is_gated(d):
            apps.append(pytest.param(d, id=d.name))
    if not apps:
        msg = f"e2e fixture directory {app_dir} contains no app directories."
        raise RuntimeError(msg)
    return apps


def _is_gated(app_dir: Path) -> bool:
    """
    Whether the app sits behind the access gate (ADR 062).

    A gated app needs an admin domain, which this suite's target does not have,
    so the deploy is refused there by design. ``test_gate.py`` deploys it on
    each proxy, with one.
    """
    hop3_toml = app_dir / "hop3.toml"
    if not hop3_toml.exists():
        return False
    access = tomllib.loads(hop3_toml.read_text()).get("access") or {}
    return access.get("require") == "auth"


TEST_APPS = _collect_apps(TEST_APPS_DIR) + _collect_apps(NIX_APPS_DIR)


@pytest.mark.e2e
@pytest.mark.parametrize("app_dir", TEST_APPS)
def test_app_deployment(app_dir: Path, deployment_target, request):
    """Test deployment of an application from apps/test-apps/ or apps/nix-apps/."""
    app_name = app_dir.name

    # No "is Nix there?" probe: the target is provisioned `--with nix` because
    # these fixtures exist (conftest `_declared_features`), and if it is not,
    # the server's own diagnosis says so by name. A probe here was a second
    # copy of where Nix lives, and it looked in root's PATH for a single-user
    # install that lives in the hop3 account's profile.
    app = AppSource(name=app_name, path=app_dir)
    with DeploymentSession(app, deployment_target) as session:
        try:
            session.deploy()  # Raises DeploymentError on failure
        except DeploymentError as e:
            # A deploy that fails for any reason, a flaky network included, is a
            # failure: reporting it as a skip hid real breakage for as long as
            # nobody read the skip reason.
            pytest.fail(f"Deploy failed: {e}")

        assert session.check_deployed(), (
            f"App {app_name} not found in deployed apps list"
        )

        # Use detailed HTTP test for better error messages
        http_result = session.test_http_detailed()
        assert http_result["passed"], (
            f"HTTP test failed for {app_name}: {http_result['message']}\n"
            f"Details: {http_result.get('details', {})}"
        )
