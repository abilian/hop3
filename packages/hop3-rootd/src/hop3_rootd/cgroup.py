# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""cgroup v2 filesystem operations for native ``[limits]`` (ADR 046 §3 / P2.2).

rootd is the only component permitted to write the cgroup hierarchy
(ADR 041). This module does the raw ``/sys/fs/cgroup`` v2 reads/writes;
``ops/cgroup.py`` orchestrates them and persists state. Keeping the kernel
poking here (analogous to the ``nft/`` package) makes the ops layer testable.

Model: cgroup v2 *unified* hierarchy only. Each app gets a leaf at::

    <CGROUP_ROOT>/hop3.slice/hop3-app-<name>.scope/

under a ``hop3.slice`` parent rootd owns. The required controllers
(``memory`` / ``cpu`` / ``pids``) must be enabled down the subtree before a
leaf can carry limits. Every path is derived here from an already-validated
``app_name`` — callers never pass a raw path (ADR 041 §1: the daemon owns the
path allow-list).

``CGROUP_ROOT`` is a module attribute so tests can point it at a tmp dir;
v1/hybrid hosts (no unified hierarchy) fail loud rather than silently
no-op — a limit that isn't enforced must never look enforced.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

# Patched in tests; production is the unified-hierarchy mountpoint.
CGROUP_ROOT: Path = Path("/sys/fs/cgroup")

HOP3_SLICE: Final[str] = "hop3.slice"
REQUIRED_CONTROLLERS: Final[tuple[str, ...]] = ("memory", "cpu", "pids")

_SCOPE_PREFIX: Final[str] = "hop3-app-"
_SCOPE_SUFFIX: Final[str] = ".scope"


class CgroupError(Exception):
    """A cgroup filesystem operation failed (dispatcher → kernel_error)."""


class CgroupUnavailableError(CgroupError):
    """No cgroup v2 unified hierarchy, or a required controller is missing.

    A declared limit cannot be enforced on this host — the caller must abort
    (strict mode) rather than run an app that only looks capped.
    """


# --- Path derivation ------------------------------------------------------


def slice_path() -> Path:
    return CGROUP_ROOT / HOP3_SLICE


def app_scope_path(app_name: str) -> Path:
    """Leaf cgroup for an app. ``app_name`` is assumed already validated."""
    return slice_path() / f"{_SCOPE_PREFIX}{app_name}{_SCOPE_SUFFIX}"


def list_scopes() -> list[str]:
    """App names that currently have a leaf under hop3.slice (for reconcile).

    Returns [] when the slice doesn't exist yet. Used to find orphan leaves
    (on disk but not in state) so a restart removes them.
    """
    sp = slice_path()
    if not sp.exists():
        return []
    names: list[str] = []
    for child in sp.iterdir():
        n = child.name
        if child.is_dir() and n.startswith(_SCOPE_PREFIX) and n.endswith(_SCOPE_SUFFIX):
            names.append(n[len(_SCOPE_PREFIX) : -len(_SCOPE_SUFFIX)])
    return names


# --- Low-level fs helpers -------------------------------------------------


def _write(path: Path, value: str) -> None:
    try:
        path.write_text(value, encoding="ascii")
    except OSError as e:
        raise CgroupError(f"could not write {path}: {e}") from e


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii")
    except OSError as e:
        raise CgroupError(f"could not read {path}: {e}") from e


def _enabled_controllers(at: Path) -> set[str]:
    """Controllers currently enabled for ``at``'s children (subtree_control)."""
    f = at / "cgroup.subtree_control"
    if not f.exists():
        return set()
    return set(_read(f).split())


def _available_controllers(at: Path) -> set[str]:
    """Controllers available to ``at`` itself (delegated from its parent)."""
    f = at / "cgroup.controllers"
    if not f.exists():
        return set()
    return set(_read(f).split())


def _enable_subtree_controllers(at: Path) -> None:
    """Enable the required controllers in ``at``'s subtree_control (idempotent).

    A controller can only be enabled here if it is in ``at``'s
    ``cgroup.controllers`` (i.e. its parent delegated it). Enabling is a no-op
    when already present, so this is safe to re-run on every deploy.
    """
    f = at / "cgroup.subtree_control"
    if not f.exists():
        raise CgroupUnavailableError(f"missing {f} (not a cgroup v2 hierarchy)")
    already = _enabled_controllers(at)
    to_add = [c for c in REQUIRED_CONTROLLERS if c not in already]
    if to_add:
        _write(f, " ".join(f"+{c}" for c in to_add))


# --- Public operations (called by ops/cgroup.py) --------------------------


def ensure_slice() -> dict[str, Any]:
    """Create ``hop3.slice`` and enable the required controllers down to it.

    Idempotent. Returns ``{slice_path, controllers}``. Raises
    ``CgroupUnavailableError`` when the host has no cgroup v2 unified
    hierarchy or is missing a required controller — the caller fails loud.
    """
    root = CGROUP_ROOT
    if not (root / "cgroup.controllers").exists():
        raise CgroupUnavailableError(
            f"no cgroup v2 unified hierarchy at {root}; boot the host with "
            "unified cgroups (systemd.unified_cgroup_hierarchy=1) to use [limits]"
        )
    root_controllers = _available_controllers(root)
    missing = [c for c in REQUIRED_CONTROLLERS if c not in root_controllers]
    if missing:
        raise CgroupUnavailableError(
            f"cgroup v2 host is missing controller(s): {', '.join(missing)}; "
            "[limits] cannot be enforced"
        )

    # Delegate controllers to hop3.slice's children, then create the slice and
    # delegate again so the per-app leaves can carry memory.max / cpu.max / etc.
    _enable_subtree_controllers(root)
    sp = slice_path()
    try:
        sp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise CgroupError(f"could not create {sp}: {e}") from e
    _enable_subtree_controllers(sp)

    return {"slice_path": str(sp), "controllers": sorted(REQUIRED_CONTROLLERS)}


def set_limits(
    app_name: str,
    *,
    memory_max: int | None = None,
    cpu_max: str | None = None,
    pids_max: int | None = None,
) -> dict[str, Any]:
    """Create/refresh the app's leaf and write the requested ``*.max`` files.

    A memory cap also sets ``memory.swap.max = 0`` so the cap is a real cap
    (no spill-to-swap), matching the Docker mapping. Returns
    ``{cgroup_path, applied}`` where ``applied`` is the subset actually set.
    """
    leaf = app_scope_path(app_name)
    try:
        leaf.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise CgroupError(f"could not create cgroup leaf {leaf}: {e}") from e

    applied: dict[str, Any] = {}
    if memory_max is not None:
        _write(leaf / "memory.max", str(memory_max))
        swap = leaf / "memory.swap.max"
        if swap.exists():
            _write(swap, "0")
        applied["memory_max"] = memory_max
    if cpu_max is not None:
        _write(leaf / "cpu.max", cpu_max)
        applied["cpu_max"] = cpu_max
    if pids_max is not None:
        _write(leaf / "pids.max", str(pids_max))
        applied["pids_max"] = pids_max

    return {"cgroup_path": str(leaf), "applied": applied}


def attach_pids(app_name: str, pids: list[int]) -> dict[str, Any]:
    """Migrate ``pids`` into the app's leaf (one write per pid to cgroup.procs).

    A pid that can't be moved (already exited → ESRCH, etc.) is collected in
    ``failed`` rather than aborting the batch; the caller decides what a
    non-empty ``failed`` means (strict mode treats it as an enforcement gap).
    """
    procs = app_scope_path(app_name) / "cgroup.procs"
    attached: list[int] = []
    failed: list[int] = []
    for pid in pids:
        try:
            procs.write_text(str(pid), encoding="ascii")
            attached.append(pid)
        except OSError:
            failed.append(pid)
    return {"attached": attached, "failed": failed}


def remove(app_name: str) -> dict[str, Any]:
    """Kill every process in the leaf, then remove it. Idempotent.

    Writes ``1`` to ``cgroup.kill`` (atomic SIGKILL of the whole subtree —
    a more reliable reap surface than ``/proc`` scanning) and rmdirs the leaf.
    Returns ``{removed, killed_pids}``; ``removed`` is False with
    ``kernel_state == "absent"`` when the leaf was already gone.
    """
    leaf = app_scope_path(app_name)
    if not leaf.exists():
        return {"removed": False, "killed_pids": [], "kernel_state": "absent"}

    killed: list[int] = []
    procs_file = leaf / "cgroup.procs"
    if procs_file.exists():
        killed = [int(p) for p in _read(procs_file).split()]
    kill_file = leaf / "cgroup.kill"
    if kill_file.exists():
        _write(kill_file, "1")

    _remove_leaf(leaf)
    return {"removed": True, "killed_pids": killed}


def _remove_leaf(leaf: Path) -> None:
    """rmdir a (now process-free) cgroup leaf.

    The kernel allows ``rmdir`` of an empty cgroup directory despite its
    virtual control files; this is a thin wrapper so tests can simulate that
    kernel semantic on an ordinary filesystem.
    """
    try:
        leaf.rmdir()
    except OSError as e:
        raise CgroupError(f"could not remove cgroup leaf {leaf}: {e}") from e


def read(app_name: str) -> dict[str, Any]:
    """Read the leaf's current caps + usage + OOM-kill count (for status).

    Missing files read as None (a leaf may not set every dimension). The
    ``oom_kill`` count comes from ``memory.events`` and drives the OOM
    surfacing in ``hop3 app status``.
    """
    leaf = app_scope_path(app_name)
    if not leaf.exists():
        raise CgroupError(f"no cgroup leaf for {app_name!r} at {leaf}")

    def _opt(name: str) -> str | None:
        f = leaf / name
        return _read(f).strip() if f.exists() else None

    return {
        "memory_max": _opt("memory.max"),
        "memory_current": _opt("memory.current"),
        "cpu_max": _opt("cpu.max"),
        "pids_max": _opt("pids.max"),
        "pids_current": _opt("pids.current"),
        "oom_kill": _parse_oom_kill(leaf),
    }


def _parse_oom_kill(leaf: Path) -> int:
    """Extract the ``oom_kill N`` counter from ``memory.events`` (0 if absent)."""
    f = leaf / "memory.events"
    if not f.exists():
        return 0
    for line in _read(f).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "oom_kill":
            try:
                return int(parts[1])
            except ValueError:
                return 0
    return 0
