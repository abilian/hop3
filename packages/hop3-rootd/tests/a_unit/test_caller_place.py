# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A caller inside the app runtime is refused, whatever its uid.

Every native app runs as hop3, the uid hop3-rootd admits, so any app's code
could call every op: root with no exploit. The caller's place tells the control
plane from the apps until each app has its own user (ADR 055).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_rootd.caller import in_app_runtime

if TYPE_CHECKING:
    from pathlib import Path


def _proc(
    root: Path, pid: int, *, cgroup: str, argv: list[str], ppid: int, comm: str = "x"
) -> None:
    entry = root / str(pid)
    entry.mkdir(parents=True)
    (entry / "cgroup").write_text(cgroup)
    (entry / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (entry / "stat").write_text(f"{pid} ({comm}) S {ppid} {pid} {pid} 0\n")


class TestUnderSystemd:
    def test_an_app_is_in_the_emperors_unit(self, tmp_path):
        _proc(tmp_path, 42, cgroup="0::/system.slice/uwsgi-hop3.service\n",
              argv=["python", "app.py"], ppid=7)  # fmt: skip
        assert in_app_runtime(42, tmp_path)

    def test_an_app_with_native_limits_is_in_its_scope(self, tmp_path):
        """`cgroup.attach_pids` moves it out of the Emperor's unit."""
        _proc(tmp_path, 42, cgroup="0::/hop3.slice/hop3-app-notes.scope\n",
              argv=["python", "app.py"], ppid=7)  # fmt: skip
        assert in_app_runtime(42, tmp_path)

    def test_hop3_server_is_not(self, tmp_path):
        _proc(tmp_path, 42, cgroup="0::/system.slice/hop3-server.service\n",
              argv=["hop3-server", "serve"], ppid=1)  # fmt: skip
        assert not in_app_runtime(42, tmp_path)

    def test_a_git_push_deploy_in_an_ssh_session_is_not(self, tmp_path):
        _proc(tmp_path, 42,
              cgroup="0::/user.slice/user-1001.slice/session-3.scope\n",
              argv=["hop3-server", "git-hook", "app"], ppid=30)  # fmt: skip
        assert not in_app_runtime(42, tmp_path)


class TestWithoutSystemd:
    """The Docker target: no per-service cgroups, so the ancestry decides."""

    def test_a_descendant_of_the_emperor_is_refused(self, tmp_path):
        _proc(tmp_path, 20, cgroup="0::/\n",
              argv=["uwsgi", "--emperor", "/home/hop3/uwsgi-enabled"], ppid=10)  # fmt: skip
        _proc(tmp_path, 30, cgroup="0::/\n", argv=["uwsgi", "--ini", "a.ini"], ppid=20)
        _proc(tmp_path, 40, cgroup="0::/\n", argv=["python", "app.py"], ppid=30)
        assert in_app_runtime(40, tmp_path)

    def test_hop3_server_under_supervisor_is_not(self, tmp_path):
        _proc(tmp_path, 10, cgroup="0::/\n", argv=["supervisord"], ppid=1)
        _proc(tmp_path, 50, cgroup="0::/\n", argv=["hop3-server", "serve"], ppid=10)
        assert not in_app_runtime(50, tmp_path)

    def test_a_command_name_with_parentheses_is_read_correctly(self, tmp_path):
        _proc(tmp_path, 20, cgroup="0::/\n", argv=["uwsgi", "--emperor", "/x"],
              ppid=1)  # fmt: skip
        _proc(tmp_path, 30, cgroup="0::/\n", argv=["evil"], ppid=20,
              comm="a) S 1 (b")  # fmt: skip
        assert in_app_runtime(30, tmp_path)


def test_a_caller_that_cannot_be_placed_is_refused(tmp_path):
    """Fails closed: an unreadable /proc entry is not a pass."""
    assert in_app_runtime(99, tmp_path)
