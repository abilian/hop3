# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Teardown process-matching: the core of reliable uWSGI app stop.

A leftover daemon holding a fixed port (e.g. owncast's RTMP 1935) makes the
next deploy of that app fail with an opaque health-check timeout — an
order-dependent heisenbug. ``_proc_belongs_to_app`` is what lets teardown find
every one of the app's processes (including Nix-``exec``'d daemons whose argv
no longer mentions the app) so it can confirm they're gone.
"""

from __future__ import annotations

from hop3.plugins.deploy.uwsgi.deployer import _proc_belongs_to_app


def test_matches_sh_wrapper_by_cmdline():
    assert _proc_belongs_to_app(
        "sh -c cd /home/hop3/apps/owncast-123/src && exec owncast",
        "/home/hop3/apps/owncast-123/src",
        "owncast-123",
    )


def test_matches_execd_nix_daemon_by_cwd():
    # The regression: argv is the Nix-store path (no app dir), but the daemon's
    # cwd is still under the app dir — pgrep -f apps/<name> would miss this.
    assert _proc_belongs_to_app(
        "/nix/store/abc123-owncast-0.1.3/bin/owncast",
        "/home/hop3/apps/owncast-123/src",
        "owncast-123",
    )


def test_matches_uwsgi_vassal_by_procname():
    # uWSGI rewrites argv to its procname-prefix "<name>:<kind>:".
    assert _proc_belongs_to_app(
        "owncast-123:web:", "/home/hop3/uwsgi-enabled", "owncast-123"
    )


def test_no_name_prefix_collision():
    # Destroying owncast-12 must NOT match owncast-123's processes.
    assert not _proc_belongs_to_app(
        "owncast-123:web:", "/home/hop3/apps/owncast-123/src", "owncast-12"
    )


def test_does_not_match_shared_emperor():
    # The shared Emperor must never be matched by a single app's teardown.
    assert not _proc_belongs_to_app(
        "uwsgi --emperor /home/hop3/uwsgi-enabled",
        "/home/hop3/uwsgi-enabled",
        "owncast-123",
    )


def test_does_not_match_unrelated_process():
    assert not _proc_belongs_to_app(
        "nginx: master process /usr/sbin/nginx", "/", "owncast-123"
    )
