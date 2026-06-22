# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TC001

"""Startup reconciliation between state.json and the inet hop3 table.

Five cases (ADR 041 §6 "Startup reconciliation"):

  - Rule in state AND in kernel, same spec → log "verified".
  - Rule in state, NOT in kernel → re-apply (kernel reload / flush).
  - Rule in kernel (in `inet hop3`), NOT in state → remove (orphan).
  - Rule in state with one spec, in kernel with a different spec → kernel
    wins; state updated; log warning. (Rare.)
  - state.json missing or corrupt → daemon refuses to start (handled in
    __main__, not here).

This module assumes the state is already loaded; it doesn't open files.
The kernel side uses `nft list_rules`; failures bubble up to the caller.

Per the Q7 caveat-emptor principle: rules outside `inet hop3` are
invisible. Operator manual mutations to managed state are unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hop3_rootd import cgroup as cg, mount as mt, proxy as px
from hop3_rootd.audit import logger
from hop3_rootd.cgroup import CgroupError
from hop3_rootd.mount import MountError
from hop3_rootd.nft.rule import (
    build_add_argv,
    build_delete_argv,
    parse_comment,
    run_nft,
)
from hop3_rootd.nft.table import ensure_table_exists, list_rules
from hop3_rootd.proxy import ProxyError, ProxyUnavailableError
from hop3_rootd.state import State, StoredRule
from hop3_rootd.validation import validate_port_spec


@dataclass(frozen=True)
class ReconcileReport:
    """Summary of what reconcile() did. Surfaced via daemon.health()."""

    verified: int = 0  # in both, matching
    reapplied: int = 0  # in state, missing from kernel, restored
    orphans_removed: int = 0  # in kernel (our table), missing from state
    state_dropped: int = 0  # in state but couldn't be re-applied; dropped


def reconcile(state: State) -> ReconcileReport:
    """Reconcile in-memory state with kernel state. Mutates `state` in place.

    Caller is responsible for persisting state.json after this returns.

    Raises NftError if the kernel is unreachable (table can't be created
    or listed); the daemon refuses to start in that case.
    """
    # Make sure the table+chain exist before anything else.
    ensure_table_exists()

    kernel_rules = list_rules()

    # Index kernel rules by their rule_id (extracted from the comment).
    # Foreign rules (rules in our table without our comment marker) shouldn't
    # exist — but if they do (operator manual edit, or a previous version
    # of rootd with a different format), we treat them as orphans below.
    by_rule_id: dict[str, int] = {}  # rule_id -> nft handle
    foreign_handles: list[int] = []
    for kr in kernel_rules:
        rid = parse_comment(kr.comment)
        if rid is None:
            foreign_handles.append(kr.handle)
        else:
            by_rule_id[rid] = kr.handle

    verified = 0
    reapplied = 0
    orphans_removed = 0
    state_dropped = 0

    # State-side rules: re-apply any missing from kernel, drop any that
    # can't be parsed.
    new_state_rules: list[StoredRule] = []
    for stored in state.rules:
        if stored.rule_id in by_rule_id:
            # Verified — both sides agree this rule exists.
            logger.info("reconcile: verified rule %s", stored.rule_id)
            new_state_rules.append(stored)
            verified += 1
            # Remove from the dict so leftover entries are orphans.
            by_rule_id.pop(stored.rule_id)
            continue

        # Missing from kernel. Try to re-apply.
        try:
            spec = validate_port_spec(stored.spec)
            argv = build_add_argv(spec, rule_id=stored.rule_id)
            run_nft(argv)
            logger.warning(
                "reconcile: re-applied missing kernel rule %s", stored.rule_id
            )
            new_state_rules.append(stored)
            reapplied += 1
        except Exception as e:
            logger.error(
                "reconcile: could not re-apply rule %s — dropping from state: %s",
                stored.rule_id,
                e,
            )
            state_dropped += 1
            # Don't append — this rule is gone.

    state.rules = new_state_rules

    # Kernel-side: anything left in by_rule_id is in our table but not in
    # state. These are orphans from a previous run that crashed before
    # persisting state. Remove them.
    for rid, handle in by_rule_id.items():
        try:
            run_nft(build_delete_argv(handle))
            logger.warning(
                "reconcile: removed orphan kernel rule %s (handle %d)", rid, handle
            )
            orphans_removed += 1
        except Exception as e:
            logger.error(
                "reconcile: failed to remove orphan rule %s (handle %d): %s",
                rid,
                handle,
                e,
            )

    # Foreign rules: rules in our table without our comment marker.
    # Per caveat-emptor, we *also* remove these — the operator shouldn't
    # be putting rules in `inet hop3`. Log loudly.
    for handle in foreign_handles:
        try:
            run_nft(build_delete_argv(handle))
            logger.warning(
                "reconcile: removed foreign (unmarked) rule with handle %d "
                "from inet hop3 table — operator should not edit this table directly",
                handle,
            )
            orphans_removed += 1
        except Exception as e:
            logger.error(
                "reconcile: failed to remove foreign rule (handle %d): %s",
                handle,
                e,
            )

    return ReconcileReport(
        verified=verified,
        reapplied=reapplied,
        orphans_removed=orphans_removed,
        state_dropped=state_dropped,
    )


# --- cgroup reconciliation (ADR 046 §3 / P2.2) ---------------------------


@dataclass(frozen=True)
class CgroupReconcileReport:
    """Summary of cgroup reconciliation. Surfaced in the startup log."""

    reasserted: int = 0  # stored leaves re-created/refreshed in the kernel
    orphans_removed: int = 0  # leaves on disk with no state row
    failed: int = 0  # stored leaves that couldn't be re-asserted


def reconcile_cgroups(state: State) -> CgroupReconcileReport:
    """Re-assert stored cgroup leaves and remove orphans at startup.

    After a reboot the cgroupfs is empty (and the apps' PIDs are gone, to be
    respawned by the Emperor); re-creating each leaf with its caps means the
    server's next deploy/reconcile re-attaches PIDs into an already-capped
    leaf. After a rootd-only restart the leaves persist and this just refreshes
    them. PIDs are never re-attached here — they belong to the Emperor.

    Raises ``CgroupUnavailableError`` when the host has no cgroup v2 hierarchy;
    the caller degrades (limits stay unenforceable, surfaced loudly) rather
    than crashing, mirroring the nft-missing path. A per-leaf failure is
    counted, not fatal: the next deploy re-applies and fails loud if it can't.
    """
    cg.ensure_slice()  # raises CgroupUnavailableError on a non-v2 host

    stored_names: set[str] = set()
    reasserted = 0
    failed = 0
    for stored in state.cgroups:
        stored_names.add(stored.app_name)
        try:
            cg.set_limits(
                stored.app_name,
                memory_max=stored.memory_max,
                cpu_max=stored.cpu_max,
                pids_max=stored.pids_max,
            )
            reasserted += 1
        except CgroupError as e:
            logger.error(
                "reconcile: could not re-assert cgroup for %s: %s",
                stored.app_name,
                e,
            )
            failed += 1

    orphans_removed = 0
    for name in cg.list_scopes():
        if name in stored_names:
            continue
        try:
            cg.remove(name)
            logger.warning("reconcile: removed orphan cgroup leaf for %s", name)
            orphans_removed += 1
        except CgroupError as e:
            logger.error("reconcile: failed to remove orphan cgroup %s: %s", name, e)

    return CgroupReconcileReport(
        reasserted=reasserted, orphans_removed=orphans_removed, failed=failed
    )


# --- mount reconciliation (ADR 046 §2 / P2.1) ----------------------------


@dataclass(frozen=True)
class MountReconcileReport:
    """Summary of mount reconciliation. Surfaced in the startup log."""

    verified: int = 0  # in state and actually mounted
    state_dropped: int = 0  # in state but not mounted (stale, e.g. post-reboot)
    orphans_removed: int = 0  # mounted under app_root with no state row


def reconcile_mounts(state: State) -> MountReconcileReport:
    """Reconcile tracked mounts with reality at startup (ADR 046 §2).

    Mounts are *not* re-asserted here: after a reboot the cgroupfs/mountns is
    empty and the app's src/ may not exist yet — the next deploy re-mounts. So
    reconcile only makes state honest: a tracked mount that isn't actually
    mounted is dropped (stale), and a mount under the app root with no state
    row is an orphan from a crashed run and is unmounted (teardown
    completeness — no leftover mount).

    Raises ``MountError`` if the app root can't be derived; the caller degrades
    (mirroring the nft/cgroup paths) rather than crashing the daemon.
    """
    kept: list = []
    verified = 0
    state_dropped = 0
    live_mountpoints: set[str] = set()
    for m in state.mounts:
        mp = mt.mountpoint_for(m.app_name, m.target)
        if mt.is_mounted(mp):
            kept.append(m)
            verified += 1
            live_mountpoints.add(str(mp))
        else:
            logger.info(
                "reconcile: dropping stale mount %s:%s (not mounted)",
                m.app_name,
                m.target,
            )
            state_dropped += 1
    state.mounts = kept

    orphans_removed = 0
    for mp_str in mt.list_mounts_under_app_root():
        if mp_str in live_mountpoints:
            continue
        try:
            mt.unmount_path(Path(mp_str))
            logger.warning("reconcile: unmounted orphan mount %s", mp_str)
            orphans_removed += 1
        except MountError as e:
            logger.error("reconcile: failed to unmount orphan %s: %s", mp_str, e)

    return MountReconcileReport(
        verified=verified, state_dropped=state_dropped, orphans_removed=orphans_removed
    )


# --- proxy reconciliation (addon exposure forwarders) --------------------


@dataclass(frozen=True)
class ProxyReconcileReport:
    """Summary of proxy reconciliation. Surfaced in the startup log."""

    reasserted: int = 0  # stored forwarders re-written/enabled in systemd
    orphans_removed: int = 0  # hop3-expose-* units on disk with no state row
    failed: int = 0  # stored forwarders that couldn't be re-asserted


def reconcile_proxies(state: State) -> ProxyReconcileReport:
    """Re-assert stored addon forwarders and remove orphans at startup.

    Unit files persist on disk and an ``enable``d socket is started by systemd
    on boot, so this is belt-and-suspenders: re-write+enable each stored
    forwarder (idempotent; restores a unit file deleted out-of-band) and remove
    any ``hop3-expose-*`` unit with no state row (a crashed expose).

    Raises ``ProxyUnavailableError`` when systemd / systemd-socket-proxyd is
    absent; the caller degrades (exposures stay down, surfaced loudly) rather
    than crashing, mirroring the nft/cgroup paths. A per-unit failure is
    counted, not fatal.
    """
    stored_units: set[str] = set()
    reasserted = 0
    failed = 0
    for sp in state.proxies:
        stored_units.add(sp.unit)
        try:
            px.add_proxy(sp.addon_type, sp.addon_name, sp.public_port, sp.target_port)
            reasserted += 1
        except ProxyUnavailableError:
            # systemd / systemd-socket-proxyd is gone — the whole subsystem is
            # down; degrade in the caller rather than mislabel every proxy.
            raise
        except ProxyError as e:
            logger.error("reconcile: could not re-assert proxy %s: %s", sp.unit, e)
            failed += 1

    orphans_removed = 0
    for unit in px.list_units():
        if unit in stored_units:
            continue
        try:
            px.remove_proxy(unit)
            logger.warning("reconcile: removed orphan proxy unit %s", unit)
            orphans_removed += 1
        except ProxyError as e:
            logger.error("reconcile: failed to remove orphan proxy %s: %s", unit, e)

    return ProxyReconcileReport(
        reasserted=reasserted, orphans_removed=orphans_removed, failed=failed
    )
