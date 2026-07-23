# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
Socket server: accept loop + dispatcher.

Single-threaded, multi-connection-accept (option B from the Q4
grilling). Per-connection request loop reads one JSON line, dispatches
to the registered op handler, writes one JSON line back. SO_PEERCRED
authenticates the caller — only UID=hop3 (and optionally root) are
admitted.

See ADR 041 §3 (IPC) and §7 (Concurrency).
"""

from __future__ import annotations

import grp
import os
import pwd
import select
import socket
import struct
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from hop3_rootd.audit import AuditEntry, AuditLog, logger, sanitise_args
from hop3_rootd.cgroup import CgroupError
from hop3_rootd.dkim import DkimError
from hop3_rootd.exec import CommandTimeoutError
from hop3_rootd.mount import MountError
from hop3_rootd.nft.rule import NftBinaryNotFoundError, NftCommandError, NftError
from hop3_rootd.ops import (
    OpContext,
    StateConflictError,
    get_registration,
)
from hop3_rootd.ops._base import DaemonStats
from hop3_rootd.ops.nginx import (
    NginxBinaryNotFoundError,
    NginxReloadNotAppliedError,
)
from hop3_rootd.postfix import PostfixError
from hop3_rootd.protocol import (
    ErrorCode,
    ProtocolError,
    Request,
    Response,
    decode_request,
    encode_response,
    error_from_protocol_error,
    error_response,
    success,
)
from hop3_rootd.state import State, save as save_state
from hop3_rootd.validation import ValidationError

# --- Constants ------------------------------------------------------------

DEFAULT_SOCKET_PATH: Final[Path] = Path("/run/hop3-rootd/socket")

# Maximum size of a single request line. The largest realistic v1 request
# (firewall.add_rule with a 200-char description and a port_range) fits
# comfortably under 1 KB; 64 KB is generous headroom and bounds the per-
# connection buffer growth so a misbehaving client can't OOM the daemon.
MAX_LINE_BYTES: Final[int] = 64 * 1024

# Allow only the hop3 user (and root for diagnostics) to connect.
# Looked up dynamically since the UID isn't fixed at compile time.
_ALLOWED_USERNAMES: Final[tuple[str, ...]] = ("hop3", "root")


# --- Peer credential check ------------------------------------------------


def _resolve_allowed_uids() -> set[int]:
    """Look up the UIDs of the allowed usernames at startup."""

    uids: set[int] = set()
    for name in _ALLOWED_USERNAMES:
        try:
            uids.add(pwd.getpwnam(name).pw_uid)
        except KeyError:
            # User doesn't exist on this host. That's fine for "root"
            # (always exists) but worth warning about for "hop3" — though
            # if hop3 doesn't exist, the daemon shouldn't have been
            # installed in the first place.
            logger.warning("user %r not present on this host", name)
    return uids


def get_peer_uid(sock: socket.socket) -> int | None:
    """
    Return the UID of the peer connected to this AF_UNIX socket.

    Uses SO_PEERCRED. Returns None on platforms that don't support it
    (e.g., macOS — but the daemon is Linux-only in practice).
    """
    try:
        # SO_PEERCRED: 12 bytes (pid, uid, gid) on Linux. The constant
        # only exists on Linux Pythons, so look it up dynamically to
        # keep type checkers (and macOS dev hosts) happy.
        so_peercred = getattr(socket, "SO_PEERCRED", None)
        if so_peercred is None:
            return None
        creds = sock.getsockopt(socket.SOL_SOCKET, so_peercred, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
        return uid
    except OSError:
        return None


# --- Dispatcher -----------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_rule_id() -> str:
    return f"rule-{uuid.uuid4().hex[:12]}"


def _make_op_context(state: State, state_path: Path, stats: DaemonStats) -> OpContext:
    """Build the OpContext passed to every op handler."""
    return OpContext(
        state=state,
        save_state=lambda: save_state(state, state_path),
        now_iso=_now_iso,
        new_rule_id=_new_rule_id,
        stats=stats,
    )


def dispatch(req: Request, ctx: OpContext) -> Response:
    """
    Look up the op, run it, translate exceptions into Response errors.

    Public for testability. Doesn't touch the audit log; see handle_one().
    """
    reg = get_registration(req.op)
    if reg is None:
        return error_response(req.id, ErrorCode.UNKNOWN_OP, f"no such op: {req.op}")

    try:
        result = reg.handler(req, ctx)
        return success(req, result)
    except ValidationError as e:
        return error_response(req.id, ErrorCode.VALIDATION_FAILED, str(e))
    except StateConflictError as e:
        return error_response(req.id, ErrorCode.STATE_CONFLICT, str(e))
    except (
        NftCommandError,
        NftBinaryNotFoundError,
        NftError,
        CgroupError,
        MountError,
        PostfixError,
        DkimError,
        NginxBinaryNotFoundError,
        NginxReloadNotAppliedError,
        CommandTimeoutError,
    ) as e:
        # nginx op failures carry an actionable, non-sensitive reason (e.g. a
        # bind/listen conflict on reload) — surface str(e) rather than scrub it
        # to an opaque internal_error.
        return error_response(req.id, ErrorCode.KERNEL_ERROR, str(e))
    except Exception as e:
        # Unexpected. Log full traceback to journald; return opaque message.
        logger.exception("unexpected error in op %s", req.op)
        return error_response(
            req.id,
            ErrorCode.INTERNAL_ERROR,
            f"internal error: {type(e).__name__}",
        )


# --- One-request handler with audit ---------------------------------------


def handle_one(line: bytes, ctx: OpContext, audit: AuditLog, caller_uid: int) -> bytes:
    """
    Decode one request line, dispatch, write audit, return response bytes.

    `line` is one full request line (with or without trailing \\n).
    Returns the encoded response bytes (terminated with \\n).
    """
    started = time.monotonic()
    request_id: str | None = None

    try:
        req = decode_request(line)
        request_id = req.id
        ctx.stats.mark_request()
    except ProtocolError as e:
        resp = error_from_protocol_error(e)
        # Audit the rejected request even though we couldn't fully parse it.
        _audit_error(audit, request_id, e.code.value, e.message, caller_uid, started)
        ctx.stats.increment_error()
        return encode_response(resp)

    resp = dispatch(req, ctx)

    # Errors always audit (even for read-only ops — they're rare and the
    # operator wants to see them). Successes audit per the op's
    # `audit=...` registration flag — read-only ops like daemon.health
    # are excluded so polling doesn't drown the log.
    duration_ms = int((time.monotonic() - started) * 1000)
    if resp.ok:
        reg = get_registration(req.op)
        if reg is not None and reg.audit:
            audit.write(
                AuditEntry(
                    ts=_now_iso(),
                    request_id=req.id,
                    caller_uid=caller_uid,
                    op=req.op,
                    args=sanitise_args(req.args),
                    outcome="applied",
                    duration_ms=duration_ms,
                    result=resp.result,
                )
            )
    else:
        audit.write(
            AuditEntry(
                ts=_now_iso(),
                request_id=req.id,
                caller_uid=caller_uid,
                op=req.op,
                args=sanitise_args(req.args),
                outcome="error",
                duration_ms=duration_ms,
                error=resp.error,
            )
        )
        ctx.stats.increment_error()

    return encode_response(resp)


def _audit_error(
    audit: AuditLog,
    request_id: str | None,
    code: str,
    message: str,
    caller_uid: int,
    started: float,
) -> None:
    """Write an audit entry for a request that couldn't be dispatched."""
    duration_ms = int((time.monotonic() - started) * 1000)
    audit.write(
        AuditEntry(
            ts=_now_iso(),
            request_id=request_id or "",
            caller_uid=caller_uid,
            op="(undecoded)",
            args={},
            outcome="error",
            duration_ms=duration_ms,
            error={"code": code, "message": message},
        )
    )


# --- Server loop ----------------------------------------------------------


def _chown_socket_to_hop3_group(path: Path) -> None:
    """
    chown ``path`` to root:hop3, best-effort.

    On systems without the hop3 group (early-install, unit tests, CI
    sandboxes) leaves ownership unchanged and warns. ``SO_PEERCRED``
    still gates connections — but mode 0o660 with the wrong group
    also gates them at the OS layer, locking out hop3-server entirely
    if the group is wrong. See notes/security.md §3.2 / FINDING-002
    in 0.5dev3.
    """
    try:
        hop3_gid = grp.getgrnam("hop3").gr_gid
    except KeyError:
        logger.warning(
            "hop3 group not found; leaving socket %s at default group "
            "ownership (only SO_PEERCRED will gate access)",
            path,
        )
        return
    try:
        os.chown(str(path), 0, hop3_gid)
    except OSError as exc:
        logger.warning("could not chown socket %s to root:hop3: %s", path, exc)


class Server:
    """
    Multi-connection-accept, single-threaded request loop.

    The socket is expected to already exist (created by systemd via the
    .socket unit, passed via fd 3). For non-systemd / tests, you can
    bind manually via Server.bind(path).

    Lifecycle:
        s = Server(state, state_path, audit_log)
        s.bind_or_inherit()
        s.run()
    """

    def __init__(self, state: State, state_path: Path, audit: AuditLog):
        self.state = state
        self.state_path = state_path
        self.audit = audit
        self.stats = DaemonStats()
        self.allowed_uids = _resolve_allowed_uids()
        self._listener: socket.socket | None = None
        self._connections: dict[int, _Connection] = {}
        self._stopping = False

    def bind(self, path: Path) -> None:
        """
        Bind a fresh socket at `path` (testing / non-systemd path).

        For systemd Type=notify with socket activation, prefer
        `inherit_systemd_socket()` — fd 3 carries an already-bound socket
        whose group ownership is set by the unit's ``SocketGroup=hop3``
        directive.

        SECURITY: when binding standalone we explicitly chown to the
        ``hop3`` group so the 0o660 mode actually grants the hop3-server
        process access. Without the chown the socket inherits the
        daemon's primary group (root in production), and the SO_PEERCRED
        UID check becomes the sole authorisation control — fine in
        principle but a configuration footgun for tests / standalone
        runs. The SocketGroup= directive in the systemd unit handles
        this for the production path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        # Remove any stale socket file.
        if path.exists():
            path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
        _chown_socket_to_hop3_group(path)
        os.chmod(str(path), 0o660)
        sock.listen(8)
        sock.setblocking(False)
        self._listener = sock
        logger.info("bound to %s", path)

    def inherit_systemd_socket(self) -> bool:
        """
        Pick up the socket activated by systemd via fd 3.

        Returns True if a systemd-supplied socket was inherited, False
        otherwise. systemd sets LISTEN_FDS=1, LISTEN_PID=<our pid>.
        """
        listen_fds = os.environ.get("LISTEN_FDS")
        listen_pid = os.environ.get("LISTEN_PID")
        if listen_fds is None or listen_pid is None:
            return False
        if int(listen_pid) != os.getpid():
            return False
        if int(listen_fds) < 1:
            return False

        # SD_LISTEN_FDS_START = 3
        sock = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(False)
        self._listener = sock
        logger.info("inherited systemd-activated socket on fd 3")
        return True

    def stop(self) -> None:
        """Request a clean shutdown. Run loop will exit on next iteration."""
        self._stopping = True

    def run(self) -> None:
        """Run the accept-and-dispatch loop until stop() is called."""
        if self._listener is None:
            raise RuntimeError(
                "server has no listener; call bind() or inherit_systemd_socket()"
            )

        listener = self._listener
        poll_fds = {listener.fileno(): listener}
        ctx = _make_op_context(self.state, self.state_path, self.stats)

        while not self._stopping:
            try:
                rlist, _, _ = select.select(list(poll_fds.keys()), [], [], 1.0)
            except (InterruptedError, OSError) as e:
                # Signal interrupt → re-check stopping flag.
                if self._stopping:
                    break
                logger.warning("select interrupted: %s", e)
                continue

            for fd in rlist:
                if fd == listener.fileno():
                    self._accept(listener, poll_fds)
                else:
                    conn = self._connections.get(fd)
                    if conn is None:
                        continue
                    self._read_one(conn, ctx, poll_fds)

        self._shutdown(poll_fds)

    def _accept(
        self, listener: socket.socket, poll_fds: dict[int, socket.socket]
    ) -> None:
        try:
            client, _ = listener.accept()
        except BlockingIOError:
            return
        client.setblocking(False)

        peer_uid = get_peer_uid(client)
        if peer_uid is None or peer_uid not in self.allowed_uids:
            logger.warning(
                "rejecting connection from uid=%s (not in allowed set %s)",
                peer_uid,
                sorted(self.allowed_uids),
            )
            client.close()
            return

        conn = _Connection(client, peer_uid)
        poll_fds[client.fileno()] = client
        self._connections[client.fileno()] = conn
        logger.debug("accepted connection from uid=%d", peer_uid)

    def _read_one(
        self, conn: _Connection, ctx: OpContext, poll_fds: dict[int, socket.socket]
    ) -> None:
        """Read one full line (or as much as we have); on full line, dispatch."""
        try:
            chunk = conn.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError as e:
            logger.debug("connection error from uid=%d: %s", conn.uid, e)
            self._close_conn(conn, poll_fds)
            return

        if not chunk:
            # Client closed cleanly.
            self._close_conn(conn, poll_fds)
            return

        conn.buffer += chunk

        # Cap buffer size: a client that sends a huge stream without a
        # newline could otherwise balloon memory until disconnect.
        if len(conn.buffer) > MAX_LINE_BYTES and b"\n" not in conn.buffer:
            logger.warning(
                "uid=%d sent %d bytes without newline; closing connection",
                conn.uid,
                len(conn.buffer),
            )
            try:
                conn.sock.sendall(
                    encode_response(
                        error_response(
                            None,
                            ErrorCode.MALFORMED_REQUEST,
                            f"line exceeds {MAX_LINE_BYTES} bytes",
                        )
                    )
                )
            except OSError:
                pass
            self._close_conn(conn, poll_fds)
            return

        # Process all complete lines available.
        while b"\n" in conn.buffer:
            line, conn.buffer = conn.buffer.split(b"\n", 1)
            try:
                response = handle_one(line, ctx, self.audit, conn.uid)
            except Exception:
                logger.exception(
                    "unexpected error handling request from uid=%d", conn.uid
                )
                response = encode_response(
                    error_response(
                        None,
                        ErrorCode.INTERNAL_ERROR,
                        "internal error",
                    )
                )
            try:
                conn.sock.sendall(response)
            except OSError as e:
                logger.debug("write failed for uid=%d: %s", conn.uid, e)
                self._close_conn(conn, poll_fds)
                return

    def _close_conn(
        self, conn: _Connection, poll_fds: dict[int, socket.socket]
    ) -> None:
        # Capture fd BEFORE close — closed sockets return -1 from fileno().
        fd = conn.sock.fileno()
        try:
            conn.sock.close()
        except OSError:
            pass
        poll_fds.pop(fd, None)
        self._connections.pop(fd, None)

    def _shutdown(self, poll_fds: dict[int, socket.socket]) -> None:
        for conn in list(self._connections.values()):
            self._close_conn(conn, poll_fds)
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        logger.info("server stopped")


class _Connection:
    """Per-client state: socket + buffer + uid."""

    __slots__ = ("buffer", "sock", "uid")

    def __init__(self, sock: socket.socket, uid: int):
        self.sock = sock
        self.uid = uid
        self.buffer = b""
