# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for OS plugin package-name validation.

The validator gates ``ensure_packages`` against shell-metacharacter
injection. ``ensure_packages`` itself shells out to native package
managers, so any regression that piped a tainted string here would
be a remote-code-execution bug.
"""

from __future__ import annotations

import pytest

from hop3.plugins.oses.arch import PACKAGES as ARCH
from hop3.plugins.oses.base import BaseOSStrategy
from hop3.plugins.oses.bsd import FREEBSD_PACKAGES, OPENBSD_PACKAGES
from hop3.plugins.oses.debian_family import PACKAGES as DEBIAN
from hop3.plugins.oses.macos import PACKAGES as MACOS
from hop3.plugins.oses.redhat_family import PACKAGES as REDHAT


def test_validates_typical_package_names():
    BaseOSStrategy._validate_package_names([
        "git",
        "python3.11",
        "py39-pip",
        "build-essential",
        "gcc-c++",
        "cairo",
    ])


def test_validates_empty_list():
    BaseOSStrategy._validate_package_names([])


@pytest.mark.parametrize(
    "bad",
    [
        "git; rm -rf /",  # command injection
        "git && evil",
        "git`whoami`",
        "git$(whoami)",
        "--option",  # argument injection (some pkg mgrs accept --)
        "/etc/passwd",  # path
        "name with spaces",
        "pkg|other",
        "name\nrm",  # newline
        "",  # empty string
    ],
)
def test_rejects_unsafe_names(bad):
    with pytest.raises(ValueError, match="Refusing unsafe package name"):
        BaseOSStrategy._validate_package_names(["git", bad])


def test_real_package_lists_pass():
    """Every PACKAGES list shipped in the tree must pass validation today."""
    for pkgs in (ARCH, DEBIAN, REDHAT, FREEBSD_PACKAGES, OPENBSD_PACKAGES, MACOS):
        BaseOSStrategy._validate_package_names(list(pkgs))
