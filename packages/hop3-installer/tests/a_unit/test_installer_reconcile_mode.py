# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`--reconcile`: what a code update runs on an existing server.

The full installer restarts uwsgi-hop3 (every app), Redis and Mailpit. Run on
every plain `hop3-deploy-server` update, it bounced every app on the box; this
mode applies the platform's own settings and runs no install step.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from hop3_installer.server_installer import installer
from hop3_installer.server_installer.cli import config_from_args, create_parser


def test_the_flag_sets_reconcile_only():
    args = create_parser().parse_args(["--reconcile"])

    assert config_from_args(args).reconcile_only is True


def test_reconcile_runs_no_install_step(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["install-server.py", "--reconcile"])
    with (
        patch.object(installer.os, "geteuid", return_value=0),
        patch.object(installer, "detect_distro", return_value="debian"),
        patch.object(installer, "reconcile_http_settings") as reconcile,
        patch.object(installer, "_run_critical_steps") as critical,
        patch.object(installer, "_configure_server") as configure,
    ):
        assert installer.main() == 0

    reconcile.assert_called_once()
    critical.assert_not_called()
    configure.assert_not_called()


def test_the_installer_sets_its_own_umask(monkeypatch):
    """
    `docker exec` handed the installer umask 0000. Redis's init script then
    created its pidfile world-writable, start-stop-daemon refused it, and the
    script exited 0 with Redis down; every file the installer created without
    a chmod was world-writable too.
    """
    monkeypatch.setattr(sys, "argv", ["install-server.py", "--reconcile"])
    seen = {}

    def reconcile():
        seen["umask"] = installer.os.umask(0)
        installer.os.umask(seen["umask"])
        return 0

    previous = installer.os.umask(0)
    try:
        with (
            patch.object(installer.os, "geteuid", return_value=0),
            patch.object(installer, "detect_distro", return_value="debian"),
            patch.object(installer, "_reconcile", reconcile),
        ):
            assert installer.main() == 0
    finally:
        installer.os.umask(previous)

    assert seen["umask"] == 0o022
