# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""Entry point for hop3-rootd.

Run via `python -m hop3_rootd` or the `hop3-rootd` console script.

Startup sequence:
  1. Configure stderr logging (captured by journald under systemd).
  2. Load state.json — refuse to start if missing or corrupt.
  3. Run reconciliation against the kernel (skipped non-fatally when the nft
     firewall backend isn't installed — the proxy/process duties don't need
     it, and crashing here would take them down too).
  4. Open the audit log (creates /var/log/hop3-rootd/ if needed).
  5. Bind/inherit the Unix socket.
  6. Notify systemd READY=1.
  7. Run the accept-and-dispatch loop until SIGTERM/SIGINT.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeVar

from hop3_rootd import cgroup as cg, proxy as px
from hop3_rootd.audit import (
    DEFAULT_AUDIT_LOG_PATH,
    AuditLog,
    configure_operational_logging,
    logger,
)
from hop3_rootd.cgroup import CgroupError, CgroupUnavailableError
from hop3_rootd.mount import MountError, MountUnavailableError
from hop3_rootd.nft.rule import NftBinaryNotFoundError, NftError
from hop3_rootd.proxy import ProxyError, ProxyUnavailableError
from hop3_rootd.reconcile import (
    reconcile,
    reconcile_cgroups,
    reconcile_mounts,
    reconcile_proxies,
)
from hop3_rootd.server import DEFAULT_SOCKET_PATH, Server
from hop3_rootd.state import (
    DEFAULT_STATE_PATH,
    State,
    StateError,
    init_empty,
    load,
    save,
)

EXIT_OK: Final[int] = 0
EXIT_STATE_ERROR: Final[int] = 2
EXIT_RECONCILE_ERROR: Final[int] = 3
EXIT_BIND_ERROR: Final[int] = 4

#: Reconcile report type — inferred per caller so ``report.reasserted`` etc.
#: type-check instead of falling back to ``Any``.
T = TypeVar("T")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hop3-rootd",
        description="Hop3 privileged operations agent (kernel-boundary executor).",
    )
    parser.add_argument(
        "--socket-path",
        type=Path,
        default=DEFAULT_SOCKET_PATH,
        help=f"Unix socket path (default: {DEFAULT_SOCKET_PATH})",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help=f"state.json path (default: {DEFAULT_STATE_PATH})",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG_PATH,
        help=f"audit log path (default: {DEFAULT_AUDIT_LOG_PATH})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="operational log level (default: INFO)",
    )
    parser.add_argument(
        "--init-state",
        action="store_true",
        help="Create an empty state.json if missing, then exit. "
        "Used by the installer at fresh-install.",
    )
    return parser.parse_args(argv)


def _sd_notify(msg: str) -> None:
    """Send a notify message to systemd. Silent no-op if not running under it."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    # Abstract sockets start with @ on Linux.
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(msg.encode("utf-8"), addr)
    except OSError as e:
        logger.warning("sd_notify failed: %s", e)


def _startup_reconcile(state: State, state_path: Path) -> bool:
    """Reconcile kernel state at startup. Return True to continue, False to abort.

    A *missing* nft backend is tolerated — the firewall subsystem degrades
    (firewall ops fail at call time, see server.dispatch) but the daemon stays
    up to serve its nginx/proxy duties, which don't need nft. Any other
    reconciliation failure is fatal per ADR 041 §6: a firewall that's expected
    to work but can't reach the kernel must refuse to start rather than run
    with an unverified security posture.
    """
    try:
        report = reconcile(state)
    except NftBinaryNotFoundError as e:
        # nft isn't installed/allow-listed here — a supported configuration
        # (containers, restricted VPSes that use Hop3 only for proxy/process
        # duties). Crashing wouldn't enforce any rules anyway; it would just
        # also kill the proxy, the failure mode this guards against.
        log = logger.error if state.rules else logger.warning
        log(
            "firewall backend unavailable (%s); skipping firewall "
            "reconciliation. %d rule(s) in state will NOT be enforced until "
            "nft is installed. Proxy/process operations are unaffected.",
            e,
            len(state.rules),
        )
        return True
    except NftError as e:
        logger.error("reconciliation failed: %s", e)
        return False

    save(state, state_path)
    logger.info(
        "reconciliation: verified=%d reapplied=%d orphans_removed=%d state_dropped=%d",
        report.verified,
        report.reapplied,
        report.orphans_removed,
        report.state_dropped,
    )
    return True


def _try_reconcile(
    state: State,
    run: Callable[[State], T],
    *,
    noun: str,
    tracked: int,
    unavailable_exc: type[Exception],
    error_exc: type[Exception],
) -> T | None:
    """Run a non-fatal reconcile; on backend-missing or error, log + degrade.

    Returns the report on success, or ``None`` when the backend was
    unavailable or errored (the caller then skips persist + log). An
    *unavailable* backend is logged at warning when nothing is tracked (a
    feature simply absent on this host) and at error when tracked state will
    go unserviced — mirroring the firewall path.

    The fatal firewall reconcile (``_startup_reconcile``) does not use this:
    it must distinguish unavailable (serve on) from a real kernel fault
    (refuse start), which needs a 3-way result rather than report-or-None.
    """
    try:
        return run(state)
    except unavailable_exc as e:
        log = logger.error if tracked else logger.warning
        log(
            "%s unavailable (%s); %d tracked item(s) will NOT be reconciled "
            "until it is present. Other operations unaffected.",
            noun,
            e,
            tracked,
        )
        return None
    except error_exc as e:
        logger.error("%s reconciliation error: %s", noun, e)
        return None


def _startup_reconcile_cgroups(state: State, state_path: Path) -> None:
    """Re-assert cgroup leaves at startup. Non-fatal by design (ADR 046 P2.2).

    A host without cgroup v2 degrades — declared limits stay unenforceable and
    fail loud at the next deploy — but the daemon keeps serving its proxy /
    process / firewall duties. Skipped entirely when there is nothing to
    reconcile, so a limits-free host never creates the slice or logs cgroup
    noise.
    """
    if not state.cgroups and not cg.slice_path().exists():
        return
    report = _try_reconcile(
        state,
        reconcile_cgroups,
        noun="cgroup v2",
        tracked=len(state.cgroups),
        unavailable_exc=CgroupUnavailableError,
        error_exc=CgroupError,
    )
    if report is None:
        return
    save(state, state_path)
    logger.info(
        "cgroup reconcile: reasserted=%d orphans_removed=%d failed=%d",
        report.reasserted,
        report.orphans_removed,
        report.failed,
    )


def _startup_reconcile_mounts(state: State, state_path: Path) -> None:
    """Reconcile tracked volume mounts at startup. Non-fatal (ADR 046 P2.1).

    Makes state honest (drops stale entries, unmounts orphans). Skipped when
    there is nothing tracked, so a volume-free host does no mountinfo work.
    """
    if not state.mounts:
        return
    report = _try_reconcile(
        state,
        reconcile_mounts,
        noun="mount backend",
        tracked=len(state.mounts),
        unavailable_exc=MountUnavailableError,
        error_exc=MountError,
    )
    if report is None:
        return
    save(state, state_path)
    logger.info(
        "mount reconcile: verified=%d state_dropped=%d orphans_removed=%d",
        report.verified,
        report.state_dropped,
        report.orphans_removed,
    )


def _startup_reconcile_proxies(state: State, state_path: Path) -> None:
    """Reconcile addon-exposure forwarders at startup. Non-fatal by design.

    Re-asserts stored forwarders and removes orphan ``hop3-expose-*`` units.
    Skipped when there is nothing tracked and no orphan units on disk, so an
    exposure-free host does no unit work.
    """
    if not state.proxies and not px.list_units():
        return
    report = _try_reconcile(
        state,
        reconcile_proxies,
        noun="systemd-socket-proxyd",
        tracked=len(state.proxies),
        unavailable_exc=ProxyUnavailableError,
        error_exc=ProxyError,
    )
    if report is None:
        return
    save(state, state_path)
    logger.info(
        "proxy reconcile: reasserted=%d orphans_removed=%d failed=%d",
        report.reasserted,
        report.orphans_removed,
        report.failed,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_operational_logging(args.log_level)

    if args.init_state:
        if args.state_path.exists():
            logger.info(
                "state.json already present at %s; nothing to do", args.state_path
            )
            return EXIT_OK
        init_empty(args.state_path)
        logger.info("created empty state.json at %s", args.state_path)
        return EXIT_OK

    try:
        state = load(args.state_path)
    except StateError as e:
        logger.error("cannot load state: %s", e)
        logger.error("refusing to start. Operator must intervene.")
        return EXIT_STATE_ERROR

    logger.info(
        "loaded state.json with %d rule(s) at %s",
        len(state.rules),
        args.state_path,
    )

    if not _startup_reconcile(state, args.state_path):
        return EXIT_RECONCILE_ERROR

    _startup_reconcile_cgroups(state, args.state_path)
    _startup_reconcile_mounts(state, args.state_path)
    _startup_reconcile_proxies(state, args.state_path)

    audit = AuditLog(args.audit_log)

    server = Server(state, args.state_path, audit)
    server.stats.mark_reconcile(datetime.now(timezone.utc).isoformat())
    if not server.inherit_systemd_socket():
        try:
            server.bind(args.socket_path)
        except OSError as e:
            logger.error("could not bind to %s: %s", args.socket_path, e)
            return EXIT_BIND_ERROR

    def _on_term(_signum, _frame):
        logger.info("received TERM/INT — shutting down")
        server.stop()

    def _on_usr1(_signum, _frame):
        logger.info("received USR1 — reopening audit log")
        audit.reopen()

    def _on_usr2(_signum, _frame):
        logger.info("received USR2 — resetting error counter")
        server.stats.reset_errors()

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    signal.signal(signal.SIGUSR1, _on_usr1)
    signal.signal(signal.SIGUSR2, _on_usr2)

    _sd_notify("READY=1")

    try:
        server.run()
    finally:
        audit.close()

    _sd_notify("STOPPING=1")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
