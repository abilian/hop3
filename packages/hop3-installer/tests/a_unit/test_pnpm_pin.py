# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The pnpm a server builds with is pinned, and reconciled on every install.

It was not: `npm install -g pnpm`, skipped entirely whenever any pnpm was
already present. An app therefore built against whatever npm's `latest` tag
pointed at on the day that box was installed, and that version kept moving
under it afterwards with no change to the app, the recipe or Hop3 — two
servers of the same Hop3 version built the same app differently.

Etherpad paid for it three times. The third was unpatchable from the recipe:
pnpm 12 removed `pnpm list --no-production`, which Etherpad's plugin migration
runs at every boot, so the build passed and the app died four seconds into
startup, on a box whose pnpm had rolled from 11 to 12 between catalog runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import deps_common


def _ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def pnpm_install(monkeypatch):
    """Drive `_install_pnpm` with a given `pnpm --version`, capture the calls."""

    def run(present: str | None, *, installs: MagicMock | None = None):
        # `pnpm --version` runs only while pnpm is on PATH.
        versions = iter([*([present] if present else []), deps_common.PNPM_VERSION])
        on_path = {"pnpm": present is not None}

        def run_cmd(cmd, **_kwargs):
            if cmd[:2] == ["pnpm", "--version"]:
                return _ok(next(versions) + "\n")
            if cmd[:3] == ["npm", "install", "-g"]:
                on_path["pnpm"] = True
            return installs or _ok()

        with (
            patch.object(deps_common, "Spinner"),
            patch.object(deps_common, "cmd_exists", lambda name: on_path["pnpm"]),
            patch.object(deps_common, "run_cmd", side_effect=run_cmd) as calls,
        ):
            deps_common._install_pnpm()
        return [c.args[0] for c in calls.call_args_list]

    return run


def test_the_pin_is_an_exact_version():
    """A major-only pin still drifts, and pnpm removes flags in minors too."""
    assert deps_common.PNPM_VERSION.count(".") == 2


def test_a_missing_pnpm_is_installed_at_the_pin(pnpm_install):
    calls = pnpm_install(None)

    assert ["npm", "install", "-g", f"pnpm@{deps_common.PNPM_VERSION}"] in calls


def test_a_wrong_version_is_replaced(pnpm_install):
    """
    The regression that broke Etherpad: any pnpm at all counted as "installed"
    and the install was skipped, so a box that had rolled forward stayed there.
    """
    calls = pnpm_install("12.4.1")

    assert ["npm", "install", "-g", f"pnpm@{deps_common.PNPM_VERSION}"] in calls


def test_the_pinned_version_is_left_alone(pnpm_install):
    """A redeploy must not reinstall what is already correct."""
    calls = pnpm_install(deps_common.PNPM_VERSION)

    assert not any(cmd[:1] == ["npm"] for cmd in calls)


def test_a_shadowing_pnpm_stops_the_install():
    """
    `npm install -g` can succeed while another pnpm stays ahead on PATH
    (corepack, the standalone script). Reporting the version we meant to
    install would be the same silent drift, with our name on it; a warning
    that the install then carried past was not much better.
    """

    def run_cmd(cmd, **_kwargs):
        if cmd[:2] == ["pnpm", "--version"]:
            return _ok("12.4.1\n")  # never moves, whatever npm did
        return _ok()

    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "cmd_exists", lambda _name: True),
        patch.object(deps_common, "run_cmd", side_effect=run_cmd),
        pytest.raises(InstallStepError, match="ahead of it on PATH"),
    ):
        deps_common._install_pnpm()
