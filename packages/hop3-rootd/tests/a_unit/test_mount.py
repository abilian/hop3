# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the mount fs/exec helper.

The exec seam is faked (``FakeExec``); mount/umount never run for real. The
fs-shaped helpers (``mountpoint_for``, ``is_mounted``, ``list_mounts_*``,
``bind_allowlist``) are exercised against tmp dirs via monkeypatched module
attributes.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_rootd import mount
from hop3_rootd.mount import MountError, MountUnavailableError

from tests.a_unit._fakes import FakeExec, fail


@pytest.fixture
def app_root(tmp_path, monkeypatch):
    # realpath so expected mountpoints match mountpoint_for's realpath output
    # (audit M1): on macOS tmp_path lives under /var -> /private/var.
    root = Path(os.path.realpath(tmp_path))
    monkeypatch.setattr(mount, "APP_ROOT", root)
    return root


@pytest.fixture
def fake_exec():
    """A FakeExec with mount/umount resolved to their allow-listed paths."""
    fake = FakeExec()
    fake.set_path("mount", "/usr/bin/mount")
    fake.set_path("umount", "/usr/bin/umount")
    return fake


# --- mountpoint_for -------------------------------------------------------


def test_mountpoint_for_builds_under_app_src(app_root):
    mp = mount.mountpoint_for("blog", "data/uploads")
    assert mp == app_root / "blog" / "src" / "data" / "uploads"


def test_mountpoint_for_rejects_escape(app_root):
    # Defense in depth: even if validation were bypassed, the containment
    # check catches a lexical '..' escape.
    with pytest.raises(MountError, match="escapes"):
        mount.mountpoint_for("blog", "../../etc/cron.d")


def test_mountpoint_for_rejects_symlink_escape(app_root):
    # audit M1 (CWE-59): a symlink planted inside src/ pointing outside the app
    # tree must be rejected. normpath would follow it silently; realpath catches
    # it. The attacker has the hop3 UID and can write to src/.
    src = app_root / "blog" / "src"
    src.mkdir(parents=True)
    (src / "escape").symlink_to("/etc")
    with pytest.raises(MountError, match="escapes"):
        mount.mountpoint_for("blog", "escape/cron.d")


# --- mount_tmpfs ----------------------------------------------------------


def test_mount_tmpfs_runs_mount_and_creates_mountpoint(app_root, fake_exec):
    result = mount.mount_tmpfs("blog", "var/cache", 268435456, "0700", exec=fake_exec)

    mp = app_root / "blog" / "src" / "var" / "cache"
    assert mp.is_dir()  # mountpoint created
    assert result == {"mountpoint": str(mp), "type": "tmpfs"}
    assert fake_exec.calls == [
        [
            "/usr/bin/mount",
            "-t",
            "tmpfs",
            "-o",
            "size=268435456,mode=0700",
            "tmpfs",
            str(mp),
        ]
    ]


def test_mount_tmpfs_without_mode_omits_mode_opt(app_root, fake_exec):
    mount.mount_tmpfs("blog", "var/cache", 1048576, exec=fake_exec)
    assert fake_exec.calls[0][4] == "size=1048576"


def test_mount_tmpfs_failure_raises(app_root, fake_exec):
    fake_exec.on(lambda argv: True, fail("mount: permission denied"))
    with pytest.raises(MountError, match="permission denied"):
        mount.mount_tmpfs("blog", "var/cache", 1048576, exec=fake_exec)


def test_mount_tmpfs_no_binary_fails_loud(app_root):
    fake = FakeExec()
    fake.set_path("mount", None)
    with pytest.raises(MountUnavailableError):
        mount.mount_tmpfs("blog", "var/cache", 1048576, exec=fake)


# --- unmount --------------------------------------------------------------


def test_unmount_absent_is_idempotent(app_root):
    with patch.object(mount, "is_mounted", return_value=False):
        result = mount.unmount("blog", "var/cache")
    assert result["unmounted"] is False
    assert result["kernel_state"] == "absent"


def test_unmount_happy_path(app_root, fake_exec):
    with patch.object(mount, "is_mounted", return_value=True):
        result = mount.unmount("blog", "var/cache", exec=fake_exec)
    assert result["unmounted"] is True
    assert result["method"] == "umount"
    assert fake_exec.calls_with("/usr/bin/umount")  # one umount happened


def test_unmount_busy_falls_back_to_lazy(app_root, fake_exec):
    # Plain umount (no -l) fails as busy; the lazy retry (-l) succeeds (default).
    fake_exec.on(lambda argv: "-l" not in argv, fail("target is busy"))
    with patch.object(mount, "is_mounted", return_value=True):
        result = mount.unmount("blog", "var/cache", exec=fake_exec)
    assert result["unmounted"] is True
    assert result["method"] == "umount -l"


def test_unmount_both_fail_raises(app_root, fake_exec):
    fake_exec.on(lambda argv: True, fail("busy"))
    with (
        patch.object(mount, "is_mounted", return_value=True),
        pytest.raises(MountError, match="could not unmount"),
    ):
        mount.unmount("blog", "var/cache", exec=fake_exec)


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


def test_is_mounted_raises_when_mountinfo_unreadable(tmp_path, monkeypatch):
    """A mountinfo that exists but can't be read is a fault, not 'not mounted'.

    Previously this returned False, which made reconcile_mounts drop a live
    mount's state row as 'stale' on a transient read error — a silent
    heisenbug. read_text on a directory raises IsADirectoryError (an OSError).
    """
    mountinfo = tmp_path / "mountinfo"
    mountinfo.mkdir()  # exists, but read_text will raise
    monkeypatch.setattr(mount, "_MOUNTINFO", mountinfo)
    with pytest.raises(MountError, match="could not read"):
        mount.is_mounted(mount.Path("/whatever"))


# --- list_mounts_under_app_root + unmount_path ----------------------------


def test_list_mounts_under_app_root(app_root, monkeypatch):
    under = app_root / "blog" / "src" / "var" / "cache"
    mountinfo = app_root / "mountinfo"
    mountinfo.write_text(
        f"36 35 0:1 / {under} rw - tmpfs tmpfs rw\n"
        "37 35 0:2 / /proc rw - proc proc rw\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mount, "_MOUNTINFO", mountinfo)
    result = mount.list_mounts_under_app_root()
    assert str(under) in result
    assert "/proc" not in result


def test_list_mounts_under_app_root_no_mountinfo(app_root, monkeypatch):
    monkeypatch.setattr(mount, "_MOUNTINFO", app_root / "nope")
    assert mount.list_mounts_under_app_root() == []


def test_unmount_path_returns_method(app_root, fake_exec):
    assert mount.unmount_path(mount.Path("/app/x"), exec=fake_exec) == "umount"


# --- bind allow-list ------------------------------------------------------


@pytest.fixture
def allowlist(tmp_path, monkeypatch):
    """A bind allow-list file + a permitted source dir under one prefix."""
    shared = tmp_path / "shared"
    (shared / "media").mkdir(parents=True)
    listfile = tmp_path / "bind-allowlist"
    listfile.write_text(f"# operator allow-list\n{shared}\n\n", encoding="utf-8")
    monkeypatch.setattr(mount, "BIND_ALLOWLIST_PATH", listfile)
    return shared


def test_bind_allowlist_parses_prefixes(allowlist):
    prefixes = mount.bind_allowlist()
    assert prefixes == [mount.Path(str(allowlist))]


def test_bind_allowlist_absent_is_deny_all(tmp_path, monkeypatch):
    monkeypatch.setattr(mount, "BIND_ALLOWLIST_PATH", tmp_path / "nope")
    assert mount.bind_allowlist() == []


# --- mount_bind -----------------------------------------------------------


def test_mount_bind_allowed_source(app_root, allowlist, fake_exec):
    source = allowlist / "media"
    result = mount.mount_bind("blog", "public/media", str(source), exec=fake_exec)

    mp = app_root / "blog" / "src" / "public" / "media"
    assert result["type"] == "bind"
    assert result["read_only"] is False
    # argv carries the realpath-resolved source the code actually used.
    assert fake_exec.calls == [["/usr/bin/mount", "--bind", result["source"], str(mp)]]


def test_mount_bind_denies_source_outside_allowlist(app_root, allowlist, fake_exec):
    outside = app_root.parent / "not-allowed"
    outside.mkdir()
    with pytest.raises(mount.MountError, match="not under any operator-allowed"):
        mount.mount_bind("blog", "public/media", str(outside), exec=fake_exec)
    assert fake_exec.calls == []  # allow-list check runs before any exec


def test_mount_bind_default_deny_when_no_allowlist(app_root, tmp_path, monkeypatch):
    monkeypatch.setattr(mount, "BIND_ALLOWLIST_PATH", tmp_path / "nope")
    src = tmp_path / "x"
    src.mkdir()
    with pytest.raises(mount.MountError, match="none configured"):
        mount.mount_bind("blog", "public/media", str(src))


def test_mount_bind_missing_source_fails_loud(app_root, allowlist):
    missing = allowlist / "does-not-exist"
    with pytest.raises(mount.MountError, match="does not exist"):
        mount.mount_bind("blog", "public/media", str(missing))


def test_mount_bind_read_only_remounts(app_root, allowlist, fake_exec):
    source = allowlist / "media"
    result = mount.mount_bind(
        "blog", "public/media", str(source), read_only=True, exec=fake_exec
    )
    assert result["read_only"] is True
    remount = fake_exec.calls[1]
    assert remount[:2] == ["/usr/bin/mount", "-o"]
    assert "remount,bind,ro" in remount


def test_mount_bind_ro_remount_failure_unmounts_and_raises(
    app_root, allowlist, fake_exec
):
    source = allowlist / "media"
    # bind ok (default), remount fails, cleanup umount ok (default).
    fake_exec.on(lambda argv: "remount,bind,ro" in argv, fail("remount denied"))
    with pytest.raises(mount.MountError, match="read-only"):
        mount.mount_bind(
            "blog", "public/media", str(source), read_only=True, exec=fake_exec
        )
    # bind, failed remount, cleanup umount — teardown must not leave it writable.
    assert len(fake_exec.calls) == 3
    assert any(c[0] == "/usr/bin/umount" for c in fake_exec.calls)
