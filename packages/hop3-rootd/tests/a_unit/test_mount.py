# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the mount fs/exec helper (mocked mount/umount)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import mount
from hop3_rootd.exec import CommandResult
from hop3_rootd.mount import MountError, MountUnavailableError


@pytest.fixture
def app_root(tmp_path, monkeypatch):
    monkeypatch.setattr(mount, "APP_ROOT", tmp_path)
    return tmp_path


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str) -> CommandResult:
    return CommandResult(argv=[], returncode=1, stdout="", stderr=stderr)


# --- mountpoint_for -------------------------------------------------------


def test_mountpoint_for_builds_under_app_src(app_root):
    mp = mount.mountpoint_for("blog", "data/uploads")
    assert mp == app_root / "blog" / "src" / "data" / "uploads"


def test_mountpoint_for_rejects_escape(app_root):
    # Defense in depth: even if validation were bypassed, normpath catches it.
    with pytest.raises(MountError, match="escapes"):
        mount.mountpoint_for("blog", "../../etc/cron.d")


# --- mount_tmpfs ----------------------------------------------------------


def test_mount_tmpfs_runs_mount_and_creates_mountpoint(app_root):
    with (
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/mount"),
        patch.object(mount, "exec_run", return_value=_ok()) as mock_run,
    ):
        result = mount.mount_tmpfs("blog", "var/cache", 268435456, "0700")

    mp = app_root / "blog" / "src" / "var" / "cache"
    assert mp.is_dir()  # mountpoint created
    assert result == {"mountpoint": str(mp), "type": "tmpfs"}
    argv = mock_run.call_args.args[0]
    assert argv == [
        "/usr/bin/mount",
        "-t",
        "tmpfs",
        "-o",
        "size=268435456,mode=0700",
        "tmpfs",
        str(mp),
    ]


def test_mount_tmpfs_without_mode_omits_mode_opt(app_root):
    with (
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/mount"),
        patch.object(mount, "exec_run", return_value=_ok()) as mock_run,
    ):
        mount.mount_tmpfs("blog", "var/cache", 1048576)
    assert mock_run.call_args.args[0][4] == "size=1048576"


def test_mount_tmpfs_failure_raises(app_root):
    with (
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/mount"),
        patch.object(mount, "exec_run", return_value=_fail("mount: permission denied")),
        pytest.raises(MountError, match="permission denied"),
    ):
        mount.mount_tmpfs("blog", "var/cache", 1048576)


def test_mount_tmpfs_no_binary_fails_loud(app_root):
    with (
        patch.object(mount, "resolve_allowed_binary", return_value=None),
        pytest.raises(MountUnavailableError),
    ):
        mount.mount_tmpfs("blog", "var/cache", 1048576)


# --- unmount --------------------------------------------------------------


def test_unmount_absent_is_idempotent(app_root):
    with patch.object(mount, "is_mounted", return_value=False):
        result = mount.unmount("blog", "var/cache")
    assert result["unmounted"] is False
    assert result["kernel_state"] == "absent"


def test_unmount_happy_path(app_root):
    with (
        patch.object(mount, "is_mounted", return_value=True),
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/umount"),
        patch.object(mount, "exec_run", return_value=_ok()),
    ):
        result = mount.unmount("blog", "var/cache")
    assert result["unmounted"] is True
    assert result["method"] == "umount"


def test_unmount_busy_falls_back_to_lazy(app_root):
    with (
        patch.object(mount, "is_mounted", return_value=True),
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/umount"),
        patch.object(mount, "exec_run", side_effect=[_fail("target is busy"), _ok()]),
    ):
        result = mount.unmount("blog", "var/cache")
    assert result["unmounted"] is True
    assert result["method"] == "umount -l"


def test_unmount_both_fail_raises(app_root):
    with (
        patch.object(mount, "is_mounted", return_value=True),
        patch.object(mount, "resolve_allowed_binary", return_value="/usr/bin/umount"),
        patch.object(
            mount, "exec_run", side_effect=[_fail("busy"), _fail("still busy")]
        ),
        pytest.raises(MountError, match="could not unmount"),
    ):
        mount.unmount("blog", "var/cache")


# --- is_mounted -----------------------------------------------------------


def test_is_mounted_reads_mountinfo(tmp_path, monkeypatch):
    mp = "/home/hop3/apps/blog/src/var/cache"
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        f"36 35 0:1 / {mp} rw,relatime shared:1 - tmpfs tmpfs rw\n", encoding="utf-8"
    )
    monkeypatch.setattr(mount, "_MOUNTINFO", mountinfo)
    assert mount.is_mounted(mount.Path(mp)) is True
    assert mount.is_mounted(mount.Path("/home/hop3/apps/other/src/x")) is False


def test_is_mounted_false_when_no_mountinfo(tmp_path, monkeypatch):
    monkeypatch.setattr(mount, "_MOUNTINFO", tmp_path / "nope")
    assert mount.is_mounted(mount.Path("/whatever")) is False
