# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`--clean` must reclaim addon storage, not just wipe /home/hop3.

Addon databases live in MySQL/PostgreSQL/Redis — separate services, outside
/home/hop3 — so wiping that directory left them behind. A later
`hop3 catalog install nextcloud` then attached to the previous nextcloud's
database, inheriting its 102 tables and its user accounts, and failed with
"The username is already being used".

Ordering is the crux: the addons can only be enumerated while Hop3's own
database still records them, so the reclaim has to run BEFORE the wipe.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig

WIPE = "rm -rf /home/hop3"


class _Backend(SSHDeployBackend):
    """Records commands; simulates a box with or without an existing install."""

    def __init__(self, *, installed: bool = True, reclaim_ok: bool = True) -> None:
        super().__init__(DeployConfig(host="example.com"))
        self.commands: list[str] = []
        self.stdins: list[str | None] = []
        self._installed = installed
        self._reclaim_ok = reclaim_ok

    def run(self, command, *, check=True, stdin=None):
        self.commands.append(command)
        self.stdins.append(stdin)
        if "hop3.db" in command and "test -x" in command:
            return SimpleNamespace(
                returncode=0 if self._installed else 1, stdout="", stderr=""
            )
        if stdin is not None:  # the reclaim script
            return SimpleNamespace(
                returncode=0 if self._reclaim_ok else 1,
                stdout="reclaimed mysql nextcloud-mysql" if self._reclaim_ok else "",
                stderr="" if self._reclaim_ok else "FAILED to reclaim mysql x: boom",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_addons_are_reclaimed_before_the_wipe() -> None:
    """
    Order matters: after `rm -rf /home/hop3` there is nothing left to read.

    The addon list comes from Hop3's own database, which that command deletes.
    """
    backend = _Backend(installed=True)

    backend.clean()

    reclaim_at = next(i for i, s in enumerate(backend.stdins) if s is not None)
    wipe_at = next(i for i, c in enumerate(backend.commands) if c == WIPE)
    assert reclaim_at < wipe_at


def test_the_reclaim_uses_hop3s_own_records() -> None:
    """Drop exactly what Hop3 provisioned — never a database someone else added."""
    backend = _Backend(installed=True)

    backend.clean()

    script = next(s for s in backend.stdins if s is not None)
    assert "AddonCredentialRepository" in script
    assert "get_addon" in script
    assert ".destroy()" in script


def test_a_failed_reclaim_aborts_rather_than_wiping() -> None:
    """
    A --clean that cannot reclaim must not proceed and claim a fresh server.

    Wiping anyway would destroy the only record of what was left behind, so the
    leftover data becomes unreachable — exactly how the orphans in this bug
    became untraceable.
    """
    backend = _Backend(installed=True, reclaim_ok=False)

    with pytest.raises(RuntimeError, match="cannot deliver the fresh server"):
        backend.clean()

    assert WIPE not in backend.commands


def test_a_box_without_hop3_reclaims_nothing() -> None:
    """First install: there is no previous state, which is not a failure."""
    backend = _Backend(installed=False)

    backend.clean()

    assert all(s is None for s in backend.stdins)
    assert WIPE in backend.commands


def test_the_reclaim_also_sweeps_databases_hop3_has_lost_track_of() -> None:
    """
    Enumerating Hop3's own records only finds what it still remembers.

    A previous --clean wiped those records while leaving the databases behind,
    so the very orphans that block the next install are invisible to it — which
    is how one server ended up with eight databases and one credential row.

    They are identifiable: Hop3 provisions `<name>_<type>` together with a
    companion role `<name>_<type>_user`, and that pair is the signature.
    """
    backend = _Backend(installed=True)

    backend.clean()

    script = next(s for s in backend.stdins if s is not None)
    assert "sweep_unowned" in script
    # The companion-role condition is what keeps this off databases that are
    # not ours; without it the sweep would be a name-prefix guess.
    assert "_user" in script
    assert "information_schema.SCHEMATA" in script


def test_the_sweep_runs_only_as_part_of_clean() -> None:
    """
    Dropping databases is only ever appropriate when wiping the installation.

    `clean()` is the single caller; nothing on the ordinary deploy path may
    reach it.
    """
    source = inspect.getsource(SSHDeployBackend)
    callers = [
        line for line in source.splitlines() if "_reclaim_addon_storage(" in line
    ]
    # One definition, one call — and the call is inside clean().
    assert len(callers) == 2, callers
    assert "self._reclaim_addon_storage()" in source
