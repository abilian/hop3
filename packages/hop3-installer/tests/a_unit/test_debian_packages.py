# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The Debian/Ubuntu package names follow what each release ships."""

from __future__ import annotations

import pytest
from hop3_installer.common import DistroInfo
from hop3_installer.server_installer.deps_common import apt_failure_reason
from hop3_installer.server_installer.deps_debian import _create_debian_package_spec


def _base_packages(distro: str, version: str, codename: str) -> list[str]:
    info = DistroInfo(
        family="debian", distro=distro, version=version, codename=codename
    )
    return _create_debian_package_spec(info).base_packages


@pytest.mark.parametrize(
    ("distro", "version", "codename", "pcre"),
    [
        ("ubuntu", "24.04", "noble", "libpcre3-dev"),
        ("ubuntu", "26.04", "resolute", "libpcre2-dev"),
        ("debian", "12", "bookworm", "libpcre3-dev"),
        ("debian", "13", "trixie", "libpcre2-dev"),
    ],
)
def test_pcre_follows_the_release(distro, version, codename, pcre):
    """Ubuntu 26.04 has no libpcre3-dev: the install stopped at apt-get."""
    packages = _base_packages(distro, version, codename)
    assert pcre in packages
    other = "libpcre2-dev" if pcre == "libpcre3-dev" else "libpcre3-dev"
    assert other not in packages


def test_no_virtual_postgresql_contrib():
    """On Ubuntu 26.04 `postgresql-contrib` is virtual, with two providers."""
    assert "postgresql-contrib" not in _base_packages("ubuntu", "26.04", "resolute")


def test_ubuntu_26_uses_mysqls_own_client_headers():
    """
    On 26.04 `mysql-server` conflicts with `mariadb-common`, which every
    libmariadb depends on: the baseline's `libmariadb-dev` removed the server.
    """
    packages = _base_packages("ubuntu", "26.04", "resolute")
    assert "libmysqlclient-dev" in packages
    assert "libmariadb-dev" not in packages


def test_mysql_adds_no_second_set_of_client_headers():
    """
    `--with mysql` added `libmysqlclient-dev` beside the base `libmariadb-dev`;
    each install removed the other, every time, without a word.
    """
    info = DistroInfo(
        family="debian", distro="ubuntu", version="24.04", codename="noble"
    )
    spec = _create_debian_package_spec(info)
    assert "libmariadb-dev" in spec.base_packages
    assert not {"libmysqlclient-dev", "libmariadb-dev"} & set(spec.mysql_packages)


def test_list_installs_never_remove_a_package():
    """apt resolves a conflict by removing the other side and still exits 0."""
    info = DistroInfo(
        family="debian", distro="ubuntu", version="24.04", codename="noble"
    )
    assert "--no-remove" in _create_debian_package_spec(info).install_flags


# apt's output on hop3-demo, Ubuntu 26.04, when the MariaDB headers an earlier
# run installed stood in the way of MySQL's.
_REFUSAL = """\
wget is already the newest version (1.25.0-2ubuntu4.4).
rsync is already the newest version (3.4.1+ds1-7ubuntu0.3).
The following packages will be REMOVED:
  libmariadb-dev
The following NEW packages will be installed:
  libmysqlclient-dev
0 upgraded, 1 newly installed, 1 to remove and 86 not upgraded.
E: Packages need to be removed but remove is disabled.
"""


def test_a_refused_removal_names_the_packages():
    """The verdict came last and the harness's summary cut it off."""
    reason = apt_failure_reason(_REFUSAL)
    assert reason.startswith("apt would remove libmariadb-dev to resolve a conflict")
    assert "libmysqlclient-dev" not in reason


def test_another_failure_gives_apts_error_line():
    output = "Reading package lists...\nE: Unable to locate package nosuch\n"
    assert apt_failure_reason(output) == "E: Unable to locate package nosuch"
