# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A local SSH port-forward tunnel backed by the system ``ssh`` binary.

Replaces the ``sshtunnel``/``paramiko`` transport with a subprocess ``ssh -N
-L`` forward. Shelling out to the platform ``ssh`` means the tunnel honours the
user's ``~/.ssh/config`` (Host aliases, ProxyJump, IdentityFile), ssh-agent,
hardware/FIDO keys, and ControlMaster multiplexing — the same credential path
the deployer already uses for remote commands — and drops the fragile paramiko
dependency (an unbounded ``paramiko`` range once resolved to 4.0, whose removal
of ``DSSKey`` crashed every ``ssh://`` deploy at construction).

Fail-loud contract (Errors Are Never Silent):

- ``start()`` returns only once the local port actually accepts a connection;
  if ``ssh`` exits first, it raises ``SshTunnelError`` carrying ssh's own stderr
  (host-key-changed, publickey denied, address-in-use, ...).
- ``ExitOnForwardFailure=yes`` makes ssh terminate rather than sit connected
  while forwarding nothing, so a lost port race is a loud exit, not a tunnel
  that silently forwards to a dead end.
- ``ServerAliveInterval``/``ServerAliveCountMax`` make ssh *exit* when the link
  dies (no application data flows over ``-N``), so ``is_active`` flips False and
  callers can report the drop instead of spinning on a dead tunnel.

Drop-in surface for the two former ``SSHTunnelForwarder`` sites (RPC client and
``hop3 tunnel``): ``start()``, ``stop()``, ``local_bind_port``, ``is_active``
(property), and ``is_alive()`` (method).
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import tempfile
import time
from typing import IO, Final

from hop3_cli.core.ssh_target import is_safe_ssh_target

_LOOPBACK: Final = "127.0.0.1"

# ssh -o values for an unattended, fail-loud forward (mirrors the deployer's
# SSHDeployBackend option set).
_CONNECT_TIMEOUT: Final = 10
_ALIVE_INTERVAL: Final = 15
_ALIVE_COUNT_MAX: Final = 3

# Readiness: wait this long for the forwarded port to accept a connection before
# giving up. Must exceed ConnectTimeout so a slow handshake is not a false miss.
_READY_TIMEOUT: Final = 20.0
_READY_POLL: Final = 0.1
_PROBE_TIMEOUT: Final = 0.5

# stop(): grace before escalating SIGTERM -> SIGKILL.
_TERM_GRACE: Final = 5.0

_MIN_PORT: Final = 1
_MAX_PORT: Final = 65535
_DEFAULT_SSH_PORT: Final = 22


class SshTunnelError(Exception):
    """A local SSH port-forward could not be established or stay up."""


def _coerce_port(value: int | str, what: str) -> int:
    """Parse and range-check a port (env vars arrive as strings)."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        msg = f"{what} must be an integer, got {value!r}"
        raise SshTunnelError(msg) from None
    if not _MIN_PORT <= port <= _MAX_PORT:
        msg = f"{what} out of range (1-65535): {port}"
        raise SshTunnelError(msg)
    return port


def _pick_free_port() -> int:
    """
    Reserve a free local port by binding :0, then release it for ssh.

    There is an unavoidable TOCTOU window between the close here and ssh binding
    the port; ``ExitOnForwardFailure=yes`` turns a lost race into a loud ssh
    exit surfaced by ``start()``, never a silent re-pick.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return sock.getsockname()[1]


def _port_open(port: int) -> bool:
    """Whether something accepts a TCP connection on 127.0.0.1:port."""
    try:
        with socket.create_connection((_LOOPBACK, port), timeout=_PROBE_TIMEOUT):
            return True
    except OSError:
        return False


class SshTunnel:
    """
    A ``ssh -N -L`` local port-forward held open by a child ssh process.

    Forwards ``127.0.0.1:<local_bind_port>`` to ``127.0.0.1:<remote_port>`` on
    the far side of the SSH connection. The local port is chosen automatically
    unless ``local_port`` pins it (``hop3 tunnel`` pins the addon's port).
    """

    def __init__(
        self,
        host: str,
        remote_port: int | str,
        *,
        user: str,
        ssh_port: int | str = _DEFAULT_SSH_PORT,
        key: str | None = None,
        local_port: int | str | None = None,
        ready_timeout: float = _READY_TIMEOUT,
    ) -> None:
        self._host = host
        self._user = user
        self._remote_port = _coerce_port(remote_port, "remote port")
        self._ssh_port = _coerce_port(ssh_port, "ssh port")
        self._key = key
        self._local_port: int | None = (
            _coerce_port(local_port, "local port") if local_port is not None else None
        )
        self._ready_timeout = ready_timeout
        self._proc: subprocess.Popen | None = None
        # ssh's stderr is spooled to a temp file, never a PIPE: over the tunnel's
        # lifetime (a `hop3 tunnel` can be held open for hours) an unread PIPE
        # would fill and deadlock ssh if the user's ssh config is verbose.
        self._stderr: IO[bytes] | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """
        Spawn ssh and block until the local port accepts a connection.

        Raises ``SshTunnelError`` (carrying ssh's stderr) if ssh exits first, or
        if the forward never becomes reachable within ``ready_timeout``.
        """
        target = f"{self._user}@{self._host}"
        if not is_safe_ssh_target(target):
            msg = f"Refusing unsafe SSH target {target!r}"
            raise SshTunnelError(msg)

        if self._local_port is None:
            self._local_port = _pick_free_port()
        local_port = self._local_port

        # A listener already on the local port would make the readiness probe
        # accept a FOREIGN process (e.g. a local Postgres on the addon's port)
        # as if it were our forward — silently routing the user there. ssh binds
        # a few hundred ms after auth, so the probe would greenlight it before
        # ExitOnForwardFailure ever fires. Refuse loudly up front instead.
        if _port_open(local_port):
            msg = f"local port {local_port} is already in use; pick another with --port"
            raise SshTunnelError(msg)

        # The sink outlives start() (it collects ssh's stderr for the tunnel's
        # whole life, read back on failure), so it can't be a `with` block.
        self._stderr = tempfile.TemporaryFile()  # ruff:ignore[open-file-with-context-handler]
        try:
            self._proc = subprocess.Popen(
                self._build_argv(target, local_port),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr,
                start_new_session=True,
            )
        except BaseException:
            # ssh binary missing, ulimit, KeyboardInterrupt mid-spawn: release
            # the sink (stop() no-ops the never-created process) and re-raise.
            self.stop()
            raise
        self._await_ready(self._proc, local_port)

    def _build_argv(self, target: str, local_port: int) -> list[str]:
        """The exact ``ssh`` command line — every value a separate argv element."""
        forward = f"{_LOOPBACK}:{local_port}:{_LOOPBACK}:{self._remote_port}"
        argv = [
            "ssh",
            "-N",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={_CONNECT_TIMEOUT}",
            "-o", f"ServerAliveInterval={_ALIVE_INTERVAL}",
            "-o", f"ServerAliveCountMax={_ALIVE_COUNT_MAX}",
            "-L", forward,
        ]  # fmt: skip
        if self._key:
            argv += ["-i", self._key]
        if self._ssh_port != _DEFAULT_SSH_PORT:
            argv += ["-p", str(self._ssh_port)]
        argv.append(target)
        return argv

    def _await_ready(self, proc: subprocess.Popen, local_port: int) -> None:
        deadline = time.monotonic() + self._ready_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                # ssh gave up before the forward was ready — surface ITS reason
                # (changed host key, publickey denied, address in use, ...).
                reason = self._read_stderr() or "ssh exited before the tunnel was ready"
                self.stop()
                msg = f"SSH tunnel to {self._host} failed: {reason}"
                raise SshTunnelError(msg)
            if _port_open(local_port):
                return
            time.sleep(_READY_POLL)

        self.stop()
        msg = (
            f"SSH tunnel to {self._host} did not become ready "
            f"within {self._ready_timeout:.0f}s"
        )
        raise SshTunnelError(msg)

    def _read_stderr(self) -> str:
        """Everything ssh wrote to stderr so far (best-effort, decoded)."""
        if self._stderr is None:
            return ""
        try:
            self._stderr.seek(0)
            return self._stderr.read().decode(errors="replace").strip()
        except (OSError, ValueError):
            return ""

    def stop(self) -> None:
        """Terminate the ssh process and clean up. Idempotent; never raises."""
        proc = self._proc
        self._proc = None
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=_TERM_GRACE)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    # Bounded: a SIGKILL'd child is normally reaped at once; a
                    # wedged D-state one can't be reaped now — don't block stop().
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        proc.wait(timeout=_TERM_GRACE)
        finally:
            # Always release the stderr sink, even if a process call raised, so
            # stop() truly never raises and never leaks the temp file.
            if self._stderr is not None:
                self._stderr.close()
                self._stderr = None

    # -- state / drop-in surface ------------------------------------------

    @property
    def is_active(self) -> bool:
        """True while the ssh process is running (read by ``hop3 tunnel``)."""
        return self._proc is not None and self._proc.poll() is None

    def is_alive(self) -> bool:
        """Method alias for ``is_active`` (read by ``Client.__del__``)."""
        return self.is_active

    @property
    def local_bind_port(self) -> int:
        """The bound local port. Available after ``start()``."""
        if self._local_port is None:
            msg = "SSH tunnel not started; no local port bound yet."
            raise SshTunnelError(msg)
        return self._local_port
