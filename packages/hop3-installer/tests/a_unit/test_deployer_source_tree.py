# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`--source-tree`: this deployer installs another release with that release's
own installer, on a fresh box.

A release's deployer up to 0.7.5 cannot run on a shared or remote Docker host
(fixed host ports, `localhost:8000`), so the upgrade chain's first hop on Docker
goes through this one. What reaches the box must still be the release's: its
bundle, built by its bundler from its module list, and rootd started from where
its installer put it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hop3_installer.constants import ROOTD_BIN
from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DEPLOYER_ROOT, DeployConfig

if TYPE_CHECKING:
    from pathlib import Path

_OLD_ROOTD = "/home/hop3/venv/bin/hop3-rootd"


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """A stand-in release tree: its own constants and its own bundler."""
    package = tmp_path / "packages/hop3-installer/src/hop3_installer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "constants.py").write_text(
        f"from pathlib import Path\nROOTD_BIN = Path({_OLD_ROOTD!r})\n"
    )
    (package / "bundler.py").write_text(
        "def bundle_installer(kind):\n    return f'# the release bundle: {kind}\\n'\n"
    )
    return tmp_path


def _config(tree: Path, **over) -> DeployConfig:
    fields = {"use_docker": True, "use_local_code": True, "clean_before": True}
    return DeployConfig(source_tree=tree, **(fields | over))


def test_the_bundle_comes_from_the_releases_own_bundler(release):
    path = _config(release).installer_path
    assert path == release / "dist" / "install-server.py"
    assert path.read_text() == "# the release bundle: server\n"


def test_rootd_starts_from_where_the_releases_installer_put_it(release):
    backend = DockerDeployBackend(_config(release))
    issued: list[str] = []

    def record(command: str, **_kwargs):
        issued.append(command)
        # supervisord is not running yet: the backend starts it.
        return SimpleNamespace(success=not command.startswith("pgrep"), stdout="")

    with patch.object(backend, "run", side_effect=record):
        backend.start_services()

    (written,) = [c for c in issued if "conf.d/hop3.conf" in c]
    assert f"command={_OLD_ROOTD} --socket-path" in written
    assert str(ROOTD_BIN) not in written


def test_the_deployers_own_tree_keeps_its_rootd_path():
    config = DeployConfig(use_docker=True)
    assert not config.installs_another_release
    # A project root of its own (a test fixture, say) is not another release.
    assert not DeployConfig(
        project_root=DEPLOYER_ROOT / "dist"
    ).installs_another_release
    assert config.rootd_bin == str(ROOTD_BIN)
    assert config.project_root == DEPLOYER_ROOT


@pytest.mark.parametrize(
    "over", [{"clean_before": False}, {"use_local_code": False}], ids=["update", "pypi"]
)
def test_another_release_is_only_a_fresh_install_from_its_tree(release, over):
    errors = _config(release, **over).validate()
    assert any("needs --from local and --clean" in e for e in errors)


def test_a_tree_without_an_installer_fails_loud(tmp_path):
    """The deployer's own package, installed in its venv, must not answer."""
    with pytest.raises(RuntimeError, match="can't read the installer"):
        _ = _config(tmp_path).rootd_bin
