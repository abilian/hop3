# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
Audit logging for hop3-rootd.

Two log streams:

  1. Operational logs to stderr, captured by journald automatically when
     the daemon runs under systemd. Standard Python `logging`.

  2. Append-only audit log at /var/log/hop3-rootd/audit.log. One JSON
     line per request, mode 0640 group hop3 so hop3-server can read
     it directly (powers `hop3 firewall history`).

See ADR 041 §13.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Self, TextIO, overload

Outcome = Literal["applied", "error"]

# --- Default audit-log path -----------------------------------------------

DEFAULT_AUDIT_LOG_PATH: Final[Path] = Path("/var/log/hop3-rootd/audit.log")
DEFAULT_AUDIT_LOG_MODE: Final[int] = 0o640


# Field names (case-insensitive) whose values get redacted in audit args.
# Conservative: false-positives are fine; false-negatives leak.
#
# The original pattern used a ``$`` end-anchor, which silently missed
# anything where the secret-marker word wasn't the last component of
# the field name — most importantly ``aws_access_key_id`` (where
# ``key`` is in the middle) and any future ``…_token_…`` style name.
# Switch to ``re.search`` semantics (no anchor) so substrings match,
# and add the common ``aws_``, ``private_``, ``access_``, ``client_id``
# prefixes that show up in real configs.
_SECRET_FIELD_RE: Final[re.Pattern[str]] = re.compile(
    r"("
    r"password"
    r"|passwd"
    r"|passphrase"
    r"|token"
    r"|secret"
    r"|credential"
    r"|api[-_]?key"
    r"|access[-_]?key"
    r"|private[-_]?key"
    r"|signing[-_]?key"
    r"|encryption[-_]?key"
    r"|key"  # catch-all (must come last; prefixes above are more specific)
    r"|aws_"  # aws_access_key_id, aws_secret_access_key
    r")",
    re.IGNORECASE,
)
_REDACTED: Final[str] = "<redacted>"


# --- Setup helpers --------------------------------------------------------


logger = logging.getLogger("hop3_rootd")


def configure_operational_logging(level: str = "INFO") -> None:
    """
    Configure the stderr logger for operational logs.

    Under systemd Type=notify, stderr is captured by journald. Format
    matches Hop3's existing structured-log idiom.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


# --- Argument sanitisation ------------------------------------------------


@overload
def sanitise_args(args: dict[str, Any]) -> dict[str, Any]: ...
@overload
def sanitise_args(args: object) -> object: ...
def sanitise_args(args: object) -> object:
    """
    Walk an arbitrary structure and redact values whose keys look secret.

    Recurses into dicts, lists, and tuples (today's rootd ops are flat
    dicts, but the redaction must hold for any nesting future ops
    introduce). Returns a structurally-equal value; never mutates input.

    Overloaded so the common ``dict`` caller gets a ``dict`` back without a
    cast, while the recursive/arbitrary case stays honestly typed as
    ``object`` (the impl legitimately accepts a top-level list or scalar too).
    """
    if isinstance(args, dict):
        out: dict[object, object] = {}
        for k, v in args.items():
            if isinstance(k, str) and _SECRET_FIELD_RE.search(k):
                out[k] = _REDACTED
            else:
                out[k] = sanitise_args(v)
        return out
    if isinstance(args, list):
        return [sanitise_args(item) for item in args]
    if isinstance(args, tuple):
        return tuple(sanitise_args(item) for item in args)
    return args


# --- Audit log writer -----------------------------------------------------


@dataclass(frozen=True)
class AuditEntry:
    """One audit-log record. Serialised as JSON, one per line."""

    ts: str  # ISO-8601 with timezone
    request_id: str
    caller_uid: int
    op: str
    args: dict[str, Any]
    outcome: Outcome
    duration_ms: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_json_line(self) -> str:
        """Serialise to a single-line JSON string (no trailing newline)."""
        d: dict[str, Any] = {
            "ts": self.ts,
            "request_id": self.request_id,
            "caller_uid": self.caller_uid,
            "op": self.op,
            "args": self.args,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
        }
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return json.dumps(d, separators=(",", ":"))


class AuditLog:
    """
    Append-only audit-log writer.

    The file is opened on construction (or first write) and re-opened on
    SIGUSR1 (logrotate-style) via `reopen()`. Writes are line-buffered:
    each call to `write()` flushes through to the kernel buffer.
    """

    def __init__(self, path: Path = DEFAULT_AUDIT_LOG_PATH) -> None:
        self.path = path
        self._fd: TextIO | None = None
        # fsync() can fail on exotic filesystems (procfs, some tmpfs). Counting
        # those failures keeps them observable (a queryable attribute) rather
        # than log-only noise; ADR 041 §13 makes audit durability a contract.
        self.fsync_failures: int = 0

    def _ensure_open(self) -> TextIO:
        if self._fd is not None and not self._fd.closed:
            return self._fd
        # Create directory if missing (StateDirectory= should have made it).
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Open append-only; create with restrictive default mode.
        self._fd = self.path.open("a", encoding="utf-8")
        # Set file mode if we just created it. ifs the file pre-existed,
        # we don't change its perms.
        try:
            self.path.chmod(DEFAULT_AUDIT_LOG_MODE)
        except OSError:
            # Best-effort; don't fail audit because chmod failed.
            logger.warning(
                "could not chmod audit log %s to %o",
                self.path,
                DEFAULT_AUDIT_LOG_MODE,
            )
        return self._fd

    def write(self, entry: AuditEntry) -> None:
        """
        Append one entry as a JSON line, flushing through to disk.

        We fsync after each entry so an audit record survives an OS crash
        in the page-cache window. The perf cost (one fsync per privileged
        op) is acceptable: rootd ops are infrequent and durability of the
        audit trail is more valuable than throughput here. ADR 041 §13.
        """
        fd = self._ensure_open()
        fd.write(entry.to_json_line() + "\n")
        fd.flush()
        try:
            os.fsync(fd.fileno())
        except OSError as exc:
            # fsync can fail on some filesystems (procfs, certain tmpfs
            # layouts). The flush above already got us through to the kernel
            # buffer; we count the failure (observable) and warn rather than
            # dropping the record or crashing the op it was auditing.
            self.fsync_failures += 1
            logger.warning(
                "audit log fsync failed (%d total): %s", self.fsync_failures, exc
            )

    def reopen(self) -> None:
        """Close + reopen the file. Hooked to SIGUSR1 (logrotate-friendly)."""
        if self._fd is not None and not self._fd.closed:
            self._fd.close()
        self._fd = None
        # Don't pre-open; next write() will open lazily.

    def close(self) -> None:
        if self._fd is not None and not self._fd.closed:
            self._fd.close()
        self._fd = None

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
