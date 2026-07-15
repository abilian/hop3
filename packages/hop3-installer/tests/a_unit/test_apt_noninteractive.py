# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Fresh-Ubuntu-24.04 apt must never hang the installer.

On a freshly-booted Ubuntu 24.04 cloud box, `apt-get install` of the base
packages hung the whole deploy for 30 minutes. Two gaps DEBIAN_FRONTEND does
not cover:
  - needrestart's whiptail "restart services?" dialog (needs NEEDRESTART_MODE=a),
  - the first-boot apt lock held by unattended-upgrades (needs a bounded
    DPkg::Lock::Timeout).
These are set on every apt call via shared constants, and run_cmd feeds EOF on
stdin so any stray stdin-reading prompt fails fast.
"""

from __future__ import annotations

import subprocess

from hop3_installer import common
from hop3_installer.common import DistroInfo
from hop3_installer.server_installer.deps_common import (
    APT_LOCK_FLAGS,
    APT_NONINTERACTIVE_ENV,
)
from hop3_installer.server_installer.deps_debian import _create_debian_package_spec


def _debian_spec():
    return _create_debian_package_spec(
        DistroInfo(family="debian", distro="ubuntu", version="24.04", codename="noble")
    )


def test_noninteractive_env_suppresses_needrestart():
    assert APT_NONINTERACTIVE_ENV["DEBIAN_FRONTEND"] == "noninteractive"
    # The essential one: DEBIAN_FRONTEND alone does NOT stop needrestart.
    assert APT_NONINTERACTIVE_ENV["NEEDRESTART_MODE"] == "a"


def test_lock_flags_are_bounded():
    assert APT_LOCK_FLAGS[0] == "-o"
    assert APT_LOCK_FLAGS[1].startswith("DPkg::Lock::Timeout=")
    # Bounded, not -1: fail loud rather than hang unbounded on the boot lock.
    timeout = int(APT_LOCK_FLAGS[1].split("=", 1)[1])
    assert 0 < timeout <= 1800


def test_debian_spec_carries_needrestart_and_lock():
    spec = _debian_spec()
    assert spec.env_vars.get("NEEDRESTART_MODE") == "a"
    assert spec.env_vars.get("DEBIAN_FRONTEND") == "noninteractive"
    # The lock flag must ride on both update and install commands.
    assert "DPkg::Lock::Timeout=600" in spec.install_flags
    assert "DPkg::Lock::Timeout=600" in spec.update_cmd


def test_run_cmd_feeds_eof_on_stdin(monkeypatch):
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(common.subprocess, "run", _fake_run)
    common.run_cmd(["echo", "hi"])
    assert captured.get("stdin") is subprocess.DEVNULL
