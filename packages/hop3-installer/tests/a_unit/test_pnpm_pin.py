# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The pnpm and npm a server builds with are pinned, and reconciled on every install.

It was not: `npm install -g pnpm`, skipped entirely whenever any pnpm was
already present. An app therefore built against whatever npm's `latest` tag
pointed at on the day that box was installed, and that version kept moving
under it afterwards with no change to the app, the recipe or Hop3 — two
servers of the same Hop3 version built the same app differently.

Etherpad paid for it three times. The third was unpatchable from the recipe:
pnpm 12 removed `pnpm list --no-production`, which Etherpad's plugin migration
runs at every boot, so the build passed and the app died four seconds into
startup, on a box whose pnpm had rolled from 11 to 12 between catalog runs.

npm is pinned the same way, in place of the one Node bundles: Node 22's npm 10
crashed installing a project scaffolded with the current NestJS CLI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import deps_common


def _ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


#: Every tool the installer pins, with its pin.
PINS = [
    ("pnpm", deps_common.PNPM_VERSION),
    ("npm", deps_common.NPM_VERSION),
]


@pytest.fixture(params=PINS, ids=[tool for tool, _ in PINS])
def pin(request) -> tuple[str, str]:
    return request.param


@pytest.fixture
def pinned_install(pin):
    """Drive `_install_pinned_tool` with a given `--version`, capture the calls."""
    tool, version = pin

    def run(present: str | None):
        # `<tool> --version` runs only while the tool is on PATH.
        versions = iter([*([present] if present else []), version])
        on_path = {tool: present is not None}

        def run_cmd(cmd, **_kwargs):
            if cmd[:2] == [tool, "--version"]:
                return _ok(next(versions) + "\n")
            if cmd[:3] == ["npm", "install", "-g"]:
                on_path[tool] = True
            return _ok()

        with (
            patch.object(deps_common, "Spinner"),
            patch.object(deps_common, "cmd_exists", lambda name: on_path[tool]),
            patch.object(deps_common, "run_cmd", side_effect=run_cmd) as calls,
        ):
            deps_common._install_pinned_tool(tool, version)
        return [c.args[0] for c in calls.call_args_list]

    return run


def test_the_pin_is_an_exact_version(pin):
    """A major-only pin still drifts, and pnpm removes flags in minors too."""
    _, version = pin
    assert version.count(".") == 2


def test_a_missing_tool_is_installed_at_the_pin(pin, pinned_install):
    tool, version = pin
    calls = pinned_install(None)

    assert ["npm", "install", "-g", f"{tool}@{version}"] in calls


def test_a_wrong_version_is_replaced(pin, pinned_install):
    """
    The regression that broke Etherpad: any pnpm at all counted as "installed"
    and the install was skipped, so a box that had rolled forward stayed there.
    """
    tool, version = pin
    calls = pinned_install("10.9.3")

    assert ["npm", "install", "-g", f"{tool}@{version}"] in calls


def test_the_pinned_version_is_left_alone(pin, pinned_install):
    """A redeploy must not reinstall what is already correct."""
    _, version = pin
    calls = pinned_install(version)

    assert not any(cmd[:3] == ["npm", "install", "-g"] for cmd in calls)


def test_a_shadowing_copy_stops_the_install(pin):
    """
    `npm install -g` can succeed while another copy stays ahead on PATH
    (corepack, the standalone script). Reporting the version we meant to
    install would be the same silent drift, with our name on it; a warning
    that the install then carried past was not much better.
    """
    tool, version = pin

    def run_cmd(cmd, **_kwargs):
        if cmd[:2] == [tool, "--version"]:
            return _ok("9.9.9\n")  # never moves, whatever npm did
        return _ok()

    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "cmd_exists", lambda _name: True),
        patch.object(deps_common, "run_cmd", side_effect=run_cmd),
        pytest.raises(InstallStepError, match="ahead of it on PATH"),
    ):
        deps_common._install_pinned_tool(tool, version)


def test_npm_is_pinned_before_pnpm():
    """pnpm is installed with npm, so npm must already be the pinned one."""
    order: list[str] = []
    with (
        patch.object(deps_common, "cmd_exists", lambda _name: True),
        patch.object(
            deps_common,
            "_install_pinned_tool",
            lambda tool, _version: order.append(tool),
        ),
        patch.object(deps_common, "_install_nodeenv"),
    ):
        deps_common.install_node_global_packages()

    assert order == ["npm", "pnpm"]
