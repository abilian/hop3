# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A requested feature's packages are installed, whatever is already on PATH."""

from __future__ import annotations

from hop3_installer.common import DistroInfo
from hop3_installer.server_installer import deps_common
from hop3_installer.server_installer.config import ServerInstallerConfig
from hop3_installer.server_installer.deps_debian import _create_debian_package_spec


def test_mysql_is_installed_even_with_mysqld_on_path(monkeypatch):
    """
    On Ubuntu 26.04 `mysql-server` was removed while its `mysqld` stayed: the
    installer saw a server, skipped the install, and found no unit to start.
    """
    installed: list[str] = []
    monkeypatch.setattr(deps_common, "cmd_exists", lambda cmd: True)
    monkeypatch.setattr(
        deps_common,
        "install_feature_packages",
        lambda name, packages, spec: installed.append(name),
    )
    spec = _create_debian_package_spec(
        DistroInfo(
            family="debian", distro="ubuntu", version="26.04", codename="resolute"
        )
    )
    config = ServerInstallerConfig(features={"mysql", "redis"})
    deps_common.install_optional_packages(config, spec, lambda: None)
    assert installed == ["MySQL", "Redis"]
