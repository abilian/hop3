# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A Docker deploy has a window with no process manager at all.

The installer provisions the box; the *deployer* then writes the supervisor
config and starts supervisord. Between those two halves there is neither systemd
nor supervisord, and every service the installer might restart or check is
legitimately not running yet.

Three places read that window as a fault — the restart after the config write,
the core-service check, and the database check. The last one set the exit code,
so a correct install ended in "Installation verification failed!" underneath
four warnings about services nothing had yet been asked to start. Meanwhile the
same run had printed "MySQL service started" and "MySQL connection verified
successfully" twenty lines earlier.

This is a *window*, not a blanket exemption: once supervisord is up (a redeploy
into a live container) the checks apply again and a real failure still fails.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from hop3_installer.common import process_manager_pending
from hop3_installer.server_installer import verify


@pytest.fixture
def supervisord(request):
    """Patch `pgrep -x supervisord` to report the requested state."""
    running = request.param

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["pgrep", "-x"]
        return subprocess.CompletedProcess(cmd, 0 if running else 1)

    with patch("subprocess.run", side_effect=fake_run):
        yield running


def test_systemd_hosts_are_never_pending():
    """systemd is always there; nothing is waiting to be set up."""
    with patch("hop3_installer.common.has_systemd", return_value=True):
        assert process_manager_pending() is False


@pytest.mark.parametrize("supervisord", [False], indirect=True)
def test_the_window_before_supervisord_is_pending(supervisord):
    with patch("hop3_installer.common.has_systemd", return_value=False):
        assert process_manager_pending() is True


@pytest.mark.parametrize("supervisord", [True], indirect=True)
def test_once_supervisord_runs_the_checks_apply_again(supervisord):
    """The guard must not outlive the window it exists for."""
    with patch("hop3_installer.common.has_systemd", return_value=False):
        assert process_manager_pending() is False


def test_service_check_defers_while_pending(capsys):
    with patch.object(verify, "process_manager_pending", return_value=True):
        verify._verify_services()

    out = capsys.readouterr().out
    assert "No process manager yet" in out
    assert "is not running" not in out


def test_mysql_liveness_defers_to_the_connection_test():
    """
    Without systemd there is no init system to ask.

    `verify_mysql_config()` runs straight after and opens a real connection, so
    it answers the question more strictly than a liveness probe would — and a
    MySQL that is genuinely down still fails there.
    """
    with patch.object(verify, "has_systemd", return_value=False):
        assert verify._is_mysql_running() is True
