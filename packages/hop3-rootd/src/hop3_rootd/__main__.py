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
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from hop3_rootd.audit import (
    DEFAULT_AUDIT_LOG_PATH,
    AuditLog,
    configure_operational_logging,
    logger,
)
from hop3_rootd.nft.rule import NftBinaryNotFoundError
from hop3_rootd.reconcile import reconcile
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
    except Exception as e:
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
