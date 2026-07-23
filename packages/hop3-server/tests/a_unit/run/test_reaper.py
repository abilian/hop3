# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Robust process detection + reaping (the core of reliable native teardown).

A leftover daemon holding a fixed port (e.g. owncast's RTMP 1935) makes the next
deploy of that app fail with an opaque 'address already in use' — an
order-dependent heisenbug. The reaper finds every one of the app's processes
(including Nix-``exec``'d daemons whose argv no longer mentions the app) and
confirms they're gone, force-killing stragglers.
"""

from __future__ import annotations

import os
import signal

from hop3.run.reaper import (
    _is_deploy_descendant,
    _protected_pids,
    app_pids,
    proc_belongs_to_app,
    reap_app_processes,
)


class TestProcBelongsToApp:
    def test_matches_execd_nix_daemon_by_cwd(self):
        # The regression: argv is the Nix-store path (no app dir), but the
        # daemon's cwd is still under the app dir — pgrep -f apps/<name> misses it.
        assert proc_belongs_to_app(
            "/nix/store/abc123-owncast-0.1.3/bin/owncast",
            "/home/hop3/apps/owncast-1/src",
            "owncast-1",
        )

    def test_matches_sh_wrapper_by_cmdline(self):
        assert proc_belongs_to_app(
            "sh -c cd /home/hop3/apps/owncast-1/src && exec owncast",
            "/home/hop3/apps/owncast-1/src",
            "owncast-1",
        )

    def test_matches_uwsgi_vassal_by_procname(self):
        assert proc_belongs_to_app("owncast-1:web:", "/home/hop3", "owncast-1")

    def test_no_match_on_name_prefix_collision(self):
        # owncast-1 must NOT match owncast-12's process (the trailing / boundary).
        assert not proc_belongs_to_app(
            "/nix/store/x/bin/owncast",
            "/home/hop3/apps/owncast-12/src",
            "owncast-1",
        )

    def test_no_match_on_shared_emperor(self):
        assert not proc_belongs_to_app(
            "uwsgi --emperor /home/hop3/uwsgi-enabled",
            "/home/hop3",
            "owncast-1",
        )


def test_app_pids_empty_for_unknown_app():
    # No process has apps/<random>/ in its cmdline/cwd (and on a non-Linux dev
    # box there is no /proc at all) — either way, nothing to reap.
    assert app_pids("no-such-app-zzz-12345") == []


def test_protected_pids_includes_self():
    # The reaper's own process (and, on Linux, its ancestors) must be protected.
    assert os.getpid() in _protected_pids()


def test_app_pids_never_reaps_its_own_process_tree(monkeypatch):
    """
    Regression: on a git-push redeploy the reaper runs inside the
    git-receive-pack subtree (cwd under apps/<name>/), so a blanket cwd match
    would SIGTERM its own ancestor mid-push. The reaper's process tree must be
    excluded even when every process "belongs" to the app.

    Forcing proc_belongs_to_app True makes every scanned PID a candidate; the
    current process (and ancestors) must still be filtered out. On a procfs-less
    host app_pids returns [] which trivially satisfies the assertion.
    """
    monkeypatch.setattr("hop3.run.reaper.proc_belongs_to_app", lambda *a, **k: True)
    pids = app_pids("anything")
    assert os.getpid() not in pids
    assert os.getppid() not in pids


def test_deploy_descendant_matches_our_build_subprocess(monkeypatch):
    # A build (bundle install / lein uberjar) is a subprocess of hop3-server —
    # 6001 -> 6000 (the toolchain shell) -> us. It shares the app's src cwd, so
    # it must be recognised as our descendant and spared from the reap.
    me = os.getpid()
    tree = {6001: 6000, 6000: me, me: 1}
    monkeypatch.setattr("hop3.run.reaper._parent_pid", tree.get)
    assert _is_deploy_descendant(6001) is True
    assert _is_deploy_descendant(6000) is True


def test_deploy_descendant_spares_emperor_supervised_runtime(monkeypatch):
    # A vassal / exec'd daemon under the uWSGI Emperor (a separate systemd tree,
    # here PID 1500) is NOT our descendant — it must still be reapable.
    tree = {9001: 1500, 1500: 1}  # vassal -> emperor -> init
    monkeypatch.setattr("hop3.run.reaper._parent_pid", tree.get)
    assert _is_deploy_descendant(9001) is False


def test_deploy_descendant_fails_safe_when_ancestry_unreadable(monkeypatch):
    # procfs unreadable / the process exited mid-walk: never claim it's ours
    # (which would wrongly spare a real straggler) — return False, so we reap.
    monkeypatch.setattr("hop3.run.reaper._parent_pid", lambda _pid: None)
    assert _is_deploy_descendant(1234) is False


def test_app_pids_skips_its_own_build_subprocess(monkeypatch):
    """
    A cwd-matched process that descends from us (the in-flight build) must be
    filtered out, even though proc_belongs_to_app matches every candidate.
    """
    monkeypatch.setattr("hop3.run.reaper.proc_belongs_to_app", lambda *a, **k: True)
    monkeypatch.setattr("hop3.run.reaper._is_deploy_descendant", lambda _pid: True)
    # On a procfs host every PID would match+descend → all skipped; on a
    # procfs-less box app_pids returns [] anyway. Either way: nothing reaped.
    assert app_pids("anything") == []


def test_reap_returns_empty_when_nothing_running(monkeypatch):
    monkeypatch.setattr("hop3.run.reaper.app_pids", lambda _name: [])
    assert reap_app_processes("ghost", timeout=0.0) == []


def test_reap_force_kills_then_reports_survivors(monkeypatch):
    # A straggler that never dies: reap must SIGTERM then SIGKILL it, and report
    # it as a survivor so the caller can report the real failure instead of a false STOPPED.
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr("hop3.run.reaper.app_pids", lambda _name: [4242])
    monkeypatch.setattr("os.kill", lambda pid, sig: sent.append((pid, sig)))
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)

    survivors = reap_app_processes("ghost", timeout=0.0)

    assert survivors == [4242]
    assert (4242, signal.SIGTERM) in sent
    assert (4242, signal.SIGKILL) in sent
