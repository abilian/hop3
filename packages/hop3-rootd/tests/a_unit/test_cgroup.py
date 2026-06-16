# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the cgroup v2 fs helper (tmp dir as CGROUP_ROOT).

A tmp directory stands in for ``/sys/fs/cgroup``: tests pre-create the
control files the kernel would auto-populate (``cgroup.controllers``,
``cgroup.subtree_control``, ``cgroup.procs`` …) so the helper's reads/writes
can be exercised without a real cgroup hierarchy.
"""

from __future__ import annotations

import shutil

import pytest
from hop3_rootd import cgroup
from hop3_rootd.cgroup import CgroupError, CgroupUnavailableError


@pytest.fixture
def cgroup_root(tmp_path, monkeypatch):
    monkeypatch.setattr(cgroup, "CGROUP_ROOT", tmp_path)
    return tmp_path


def _mk(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii")


# --- ensure_slice ---------------------------------------------------------


def test_ensure_slice_no_unified_hierarchy_fails_loud(cgroup_root):
    # No cgroup.controllers at the root → not a v2 unified hierarchy.
    with pytest.raises(CgroupUnavailableError, match="unified"):
        cgroup.ensure_slice()


def test_ensure_slice_missing_controller_fails_loud(cgroup_root):
    _mk(cgroup_root / "cgroup.controllers", "cpu io")  # no memory / pids
    _mk(cgroup_root / "cgroup.subtree_control", "")
    with pytest.raises(CgroupUnavailableError, match="missing controller"):
        cgroup.ensure_slice()


def test_ensure_slice_creates_slice_and_enables_controllers(cgroup_root):
    _mk(cgroup_root / "cgroup.controllers", "memory cpu pids io")
    _mk(cgroup_root / "cgroup.subtree_control", "")
    # The kernel auto-populates a new cgroup's control files; simulate it.
    _mk(cgroup_root / "hop3.slice" / "cgroup.subtree_control", "")

    result = cgroup.ensure_slice()

    assert result["slice_path"].endswith("hop3.slice")
    assert (cgroup_root / "hop3.slice").is_dir()
    # Controllers delegated at both levels.
    root_sc = (cgroup_root / "cgroup.subtree_control").read_text()
    slice_sc = (cgroup_root / "hop3.slice" / "cgroup.subtree_control").read_text()
    for c in ("memory", "cpu", "pids"):
        assert f"+{c}" in root_sc
        assert f"+{c}" in slice_sc


def test_enable_subtree_controllers_is_idempotent(cgroup_root):
    at = cgroup_root / "x"
    # Already-enabled controllers (as the kernel reports them, no '+').
    _mk(at / "cgroup.subtree_control", "memory cpu pids")
    cgroup._enable_subtree_controllers(at)
    # Nothing to add → file unchanged.
    assert (at / "cgroup.subtree_control").read_text() == "memory cpu pids"


# --- set_limits -----------------------------------------------------------


def test_set_limits_writes_all_caps_and_swap_off(cgroup_root):
    leaf = cgroup.app_scope_path("blog")
    # Pre-create the leaf + memory.swap.max (the kernel would provide it).
    _mk(leaf / "memory.swap.max", "max")

    result = cgroup.set_limits(
        "blog", memory_max=536870912, cpu_max="150000 100000", pids_max=256
    )

    assert (leaf / "memory.max").read_text() == "536870912"
    assert (leaf / "memory.swap.max").read_text() == "0"  # a real cap, no spill
    assert (leaf / "cpu.max").read_text() == "150000 100000"
    assert (leaf / "pids.max").read_text() == "256"
    assert result["applied"] == {
        "memory_max": 536870912,
        "cpu_max": "150000 100000",
        "pids_max": 256,
    }


def test_set_limits_partial_only_writes_given(cgroup_root):
    leaf = cgroup.app_scope_path("blog")
    cgroup.set_limits("blog", pids_max=64)
    assert (leaf / "pids.max").read_text() == "64"
    assert not (leaf / "memory.max").exists()
    assert not (leaf / "cpu.max").exists()


# --- attach_pids ----------------------------------------------------------


def test_attach_pids_writes_each_pid(cgroup_root):
    leaf = cgroup.app_scope_path("blog")
    _mk(leaf / "cgroup.procs", "")
    result = cgroup.attach_pids("blog", [10, 11])
    assert result["attached"] == [10, 11]
    assert result["failed"] == []


def test_attach_pids_reports_failures_for_missing_leaf(cgroup_root):
    # No leaf dir → writing cgroup.procs fails → all pids reported failed.
    result = cgroup.attach_pids("ghost", [10, 11])
    assert result["attached"] == []
    assert result["failed"] == [10, 11]


# --- remove ---------------------------------------------------------------


def test_remove_absent_leaf_is_idempotent(cgroup_root):
    result = cgroup.remove("ghost")
    assert result == {"removed": False, "killed_pids": [], "kernel_state": "absent"}


def test_remove_kills_subtree_and_reports(cgroup_root, monkeypatch):
    leaf = cgroup.app_scope_path("blog")
    _mk(leaf / "cgroup.procs", "100\n200\n")
    _mk(leaf / "cgroup.kill", "")
    # The kernel rmdirs a cgroup despite its virtual control files; on a real
    # fs the leftover files block rmdir, so simulate the kernel semantic.
    monkeypatch.setattr(cgroup, "_remove_leaf", shutil.rmtree)

    result = cgroup.remove("blog")

    assert result["removed"] is True
    assert result["killed_pids"] == [100, 200]
    assert (leaf / "cgroup.kill").exists() is False  # whole leaf gone
    assert not leaf.exists()


# --- read -----------------------------------------------------------------


def test_read_returns_caps_usage_and_oom_kill(cgroup_root):
    leaf = cgroup.app_scope_path("blog")
    _mk(leaf / "memory.max", "536870912\n")
    _mk(leaf / "memory.current", "12345\n")
    _mk(leaf / "cpu.max", "150000 100000\n")
    _mk(leaf / "pids.max", "256\n")
    _mk(leaf / "pids.current", "7\n")
    _mk(leaf / "memory.events", "low 0\nhigh 0\nmax 4\noom 1\noom_kill 3\n")

    result = cgroup.read("blog")

    assert result["memory_max"] == "536870912"
    assert result["cpu_max"] == "150000 100000"
    assert result["pids_current"] == "7"
    assert result["oom_kill"] == 3


def test_read_missing_leaf_fails_loud(cgroup_root):
    with pytest.raises(CgroupError, match="no cgroup leaf"):
        cgroup.read("ghost")


# --- list_scopes ----------------------------------------------------------


def test_list_scopes_returns_app_names(cgroup_root):
    slice_dir = cgroup_root / "hop3.slice"
    (slice_dir / "hop3-app-blog.scope").mkdir(parents=True)
    (slice_dir / "hop3-app-wiki.scope").mkdir()
    (slice_dir / "system.scope").mkdir()  # not one of ours
    _mk(slice_dir / "cgroup.subtree_control", "")  # a file, not a scope dir
    assert set(cgroup.list_scopes()) == {"blog", "wiki"}


def test_list_scopes_empty_when_no_slice(cgroup_root):
    assert cgroup.list_scopes() == []
