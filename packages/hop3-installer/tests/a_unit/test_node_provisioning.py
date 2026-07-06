# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Node.js must come from NodeSource (Node 22 LTS), not the distro's apt.

Debian/Ubuntu ship Node 18 (EOL), which modern JS frameworks reject (Astro
>=22.12, Etherpad/pnpm >=22.13). The installer installs Node from NodeSource
so every build step gets a supported runtime. These tests pin that contract:
the distro `nodejs`/`npm` packages are gone, and the NodeSource setup runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_installer.common import CommandError
from hop3_installer.server_installer import baselines, deps_common, deps_debian


def test_distro_node_packages_are_not_apt_installed():
    # Pulling the distro `nodejs`/`npm` would install Node 18 (and `npm`
    # drags Node 18 in as a dependency), defeating the NodeSource install.
    assert "nodejs" not in deps_debian.DEBIAN_BASE_PACKAGES
    assert "npm" not in deps_debian.DEBIAN_BASE_PACKAGES


def _ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_install_node_toolchain_uses_nodesource():
    with (
        patch.object(deps_debian, "Spinner"),
        patch.object(deps_debian, "run_cmd") as run_cmd,
    ):
        run_cmd.side_effect = [
            _ok(),  # curl fetch of setup script
            _ok(),  # bash setup script
            _ok(),  # apt-get install nodejs
            _ok("v22.13.1\n"),  # node --version
        ]
        deps_debian._install_node_toolchain()

    calls = [c.args[0] for c in run_cmd.call_args_list]
    # The NodeSource setup script is fetched...
    assert any(
        "https://deb.nodesource.com/setup_22.x" in arg for call in calls for arg in call
    )
    # ...and `nodejs` is installed from the configured repo (no distro `npm`),
    # with the fresh-boot apt lock timeout (APT_LOCK_FLAGS).
    assert ["apt-get", "install", "-y", *deps_common.APT_LOCK_FLAGS, "nodejs"] in calls


def test_install_node_toolchain_falls_back_when_setup_unfetchable():
    # Offline/mirrored host: the setup script can't be fetched. Still install
    # *some* Node so the build path exists (loudly, since it may be too old).
    with (
        patch.object(deps_debian, "Spinner"),
        patch.object(deps_debian, "run_cmd") as run_cmd,
        patch.object(deps_debian, "print_warning") as warn,
    ):
        run_cmd.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="curl: (6)"),  # fetch fails
            _ok("v18.19.1\n"),  # apt-get install nodejs npm (fallback)
            _ok("v18.19.1\n"),  # node --version
        ]
        deps_debian._install_node_toolchain()

    calls = [c.args[0] for c in run_cmd.call_args_list]
    expected = [
        "apt-get",
        "install",
        "-y",
        *deps_common.APT_LOCK_FLAGS,
        "nodejs",
        "npm",
    ]
    assert expected in calls
    assert warn.called  # the fallback (old Node) is surfaced, not silent


def test_catalogue_baseline_filters_nodesource_packages(monkeypatch):
    # libnode-dev/nodejs/npm in the baseline would make apt try to install the
    # distro Node alongside NodeSource — an unsatisfiable conflict. They must be
    # dropped before the apt call.
    monkeypatch.setattr(
        baselines,
        "BASELINE_PACKAGES",
        {"debian": ["ffmpeg", "libnode-dev", "nodejs", "npm", "node-gyp"]},
    )
    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "run_cmd", return_value=_ok()) as run_cmd,
    ):
        deps_common.install_catalogue_baseline("debian")

    install_cmd = run_cmd.call_args_list[0].args[0]
    assert "ffmpeg" in install_cmd
    for node_pkg in ("libnode-dev", "nodejs", "npm", "node-gyp"):
        assert node_pkg not in install_cmd


def test_catalogue_baseline_aborts_loudly_on_apt_failure(monkeypatch):
    # The conflict (or any apt failure) must abort, not warn-and-continue: a
    # broken baseline leaves native-profile apps unbuildable and used to hide
    # behind a warning while every Node app failed downstream.
    monkeypatch.setattr(baselines, "BASELINE_PACKAGES", {"debian": ["ffmpeg"]})
    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "print_error"),
        patch.object(
            deps_common,
            "run_cmd",
            return_value=MagicMock(
                returncode=100, stdout="", stderr="held broken packages"
            ),
        ),
        pytest.raises(CommandError),
    ):
        deps_common.install_catalogue_baseline("debian")


def test_nodeenv_installed_from_pypi_venv_not_npm(monkeypatch, tmp_path):
    # The npm package 'nodeenv' is an unrelated test utility with no binary; the
    # real tool is PyPI's nodeenv. It must be pip-installed into a venv and
    # symlinked onto PATH — never `npm install -g nodeenv`.
    monkeypatch.setattr(deps_common, "_NODEENV_BIN", tmp_path / "usr" / "nodeenv")
    monkeypatch.setattr(deps_common, "_NODEENV_VENV", tmp_path / "venv")
    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "run_cmd", return_value=_ok()) as run_cmd,
        patch.object(deps_common, "create_symlink", return_value=True) as symlink,
    ):
        deps_common._install_nodeenv()

    cmds = [c.args[0] for c in run_cmd.call_args_list]
    assert any(c[:3] == ["python3", "-m", "venv"] for c in cmds)
    assert any("pip" in c[0] and "nodeenv" in c for c in cmds)
    # Never the (wrong) npm package.
    assert not any("npm" in part for c in cmds for part in c)
    symlink.assert_called_once()
