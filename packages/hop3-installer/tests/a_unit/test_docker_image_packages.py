# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The Docker test image pre-installs what the installer installs, and nothing else.

A fresh `hop3-deploy-server --docker` spent 13 of its 17.5 minutes downloading
the same packages into every new container. The image now holds them, so the
installer's own apt calls find them installed and still run. Its lists are
files derived from the installer's code: a package the image held and the
installer did not would hide an installer that forgot it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_installer.common import DistroInfo
from hop3_installer.server_installer.baselines import BASELINE_PACKAGES
from hop3_installer.server_installer.deps_common import (
    DOTNET_SDK_VERSIONS,
    _is_nodesource_provided,
)
from hop3_installer.server_installer.deps_debian import (
    _create_debian_package_spec,
    package_renames,
)

DOCKER_DIR = Path(__file__).parents[2] / "docker"
NOBLE = DistroInfo(family="debian", distro="ubuntu", version="24.04", codename="noble")


def _no_recommends() -> list[str]:
    """The base list and the catalogue baseline: both use --no-install-recommends."""
    renames = package_renames(NOBLE)
    baseline = [renames.get(name, name) for name in BASELINE_PACKAGES["debian"]]
    baseline = [name for name in baseline if not _is_nodesource_provided(name)]
    return sorted({*_create_debian_package_spec(NOBLE).base_packages, *baseline})


def _with_recommends() -> list[str]:
    """Go and the .NET SDKs, which the installer installs with their recommends."""
    return sorted(["golang-go", *(f"dotnet-sdk-{v}" for v in DOTNET_SDK_VERSIONS)])


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("noble-packages.txt", _no_recommends()),
        ("noble-packages-with-recommends.txt", _with_recommends()),
    ],
)
def test_the_image_lists_match_the_installer(filename: str, expected: list[str]):
    listed = (DOCKER_DIR / filename).read_text().split()
    assert listed == expected, (
        f"{filename} drifted from the installer; write it as:\n" + "\n".join(expected)
    )
