# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""Safe subprocess wrapper for hop3-rootd.

The discipline:

  - `run()` only takes a list of strings (argv form), never a string.
  - `shell=True` is structurally impossible (we don't expose a shell flag).
  - The first element (binary path) is checked against an allow-list.
  - Timeout is always set; default 30s.
  - stdout and stderr are always captured; output is decoded as UTF-8.
  - Return value is a typed `CommandResult` dataclass.

This is the only path through which rootd invokes external processes.
Every privileged action ultimately goes through here. See ADR 041 §10.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

# --- Allow-list of binary paths --------------------------------------------
# Absolute paths only. Anything else is rejected with InvalidBinaryError.
# Adding a new entry is a deliberate decision (and should be a separate
# code review).
ALLOWED_BINARIES: Final[frozenset[str]] = frozenset({
    "/usr/sbin/nft",
    "/sbin/nft",  # some distros
    "/usr/bin/systemctl",
    "/bin/systemctl",  # some distros
    "/usr/sbin/nginx",
    "/sbin/nginx",  # some distros
    # Email loopback relay (ADR 054) — configure + rebuild the sasl map.
    "/usr/sbin/postfix",
    "/usr/sbin/postmap",
    # Volume mounts (ADR 046 §2 / P2.1) — tmpfs and bind volumes.
    "/usr/bin/mount",
    "/bin/mount",  # some distros
    "/usr/bin/umount",
    "/bin/umount",  # some distros
})


DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0


# --- Binary resolution ----------------------------------------------------


def resolve_allowed_binary(name: str) -> str | None:
    """Return the absolute path of `name` from PATH iff it's on the allow-list.

    Used by callers that want to detect "is this binary available *and*
    permitted" before constructing an argv. Returns None when either
    condition fails — the caller decides whether absence is a fatal error
    or a fall-through.

    Defense in depth: even if PATH points at a rogue binary, `run()`
    would refuse it; this lets the rejection happen with a clearer
    message at the call site.
    """
    candidate = shutil.which(name)
    if candidate is None:
        return None
    if candidate not in ALLOWED_BINARIES:
        return None
    return candidate


# --- Exceptions ------------------------------------------------------------


class ExecError(Exception):
    """Base for any error from the exec wrapper."""


class InvalidBinaryError(ExecError):
    """Raised when a command's first element is not on the allow-list."""

    def __init__(self, binary: str):
        super().__init__(f"binary not in allow-list: {binary!r}")
        self.binary = binary


class CommandTimeoutError(ExecError):
    """Raised when a command exceeds its timeout."""

    def __init__(self, argv: list[str], timeout: float):
        super().__init__(f"command timed out after {timeout}s: {argv}")
        self.argv = argv
        self.timeout = timeout


# --- Result type -----------------------------------------------------------


@dataclass(frozen=True)
class CommandResult:
    """Captured output of a successful or failed command run.

    A command is "run" if it executed at all (regardless of return code).
    Use `result.success` for the boolean "exit code was 0?".
    """

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


# --- The wrapper -----------------------------------------------------------


def run(
    argv: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    stdin_data: bytes | None = None,
    extra_env: dict[str, str] | None = None,
    check: bool = False,
) -> CommandResult:
    """Run an external command safely.

    Args:
        argv: The command and its arguments. Must be a non-empty list of
            strings. argv[0] must be on ALLOWED_BINARIES (absolute path).
        timeout: Wall-clock timeout in seconds. Default 30s.
        stdin_data: Optional bytes to send to the process's stdin.
        extra_env: Optional dict of env vars to overlay on the parent env.
            (We don't override PATH or LANG by default — but callers can.)
        check: If True, raise CalledProcessError on non-zero exit. Default False
            because callers usually want to inspect stderr themselves.

    Returns:
        CommandResult with returncode, stdout, stderr (text-decoded).

    Raises:
        ValueError: argv is empty or not a list.
        InvalidBinaryError: argv[0] is not on the allow-list.
        CommandTimeoutError: process didn't exit within `timeout`.
        subprocess.CalledProcessError: only if `check=True` and exit != 0.
    """
    if not isinstance(argv, list):
        raise TypeError(f"argv must be a list, got {type(argv).__name__}")
    if not argv:
        raise ValueError("argv must be non-empty")
    if not all(isinstance(a, str) for a in argv):
        raise TypeError("argv must contain only strings")

    binary = argv[0]
    if binary not in ALLOWED_BINARIES:
        raise InvalidBinaryError(binary)

    # Defense in depth: also check the binary actually exists at the path.
    # This catches misconfigured allow-list entries quickly, with a clearer
    # error than "exec format error" or similar from the kernel.
    if not Path(binary).is_file():
        raise InvalidBinaryError(f"{binary} (not present on filesystem)")

    env: dict[str, str] | None = None
    if extra_env is not None:
        env = {**os.environ, **extra_env}

    try:
        proc = subprocess.run(
            argv,
            input=stdin_data,
            capture_output=True,
            timeout=timeout,
            check=check,
            env=env,
            # Explicit: no shell, ever.
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise CommandTimeoutError(argv, timeout) from e

    return CommandResult(
        argv=list(argv),
        returncode=proc.returncode,
        stdout=_decode(proc.stdout),
        stderr=_decode(proc.stderr),
    )


def _decode(b: bytes | str | None) -> str:
    """Decode bytes to UTF-8 with replacement for any invalid sequences."""
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    return b.decode("utf-8", errors="replace")


# --- Exec seam (dependency injection / testability) ----------------------


class Exec(Protocol):
    """Capability for running allow-listed binaries and resolving them.

    The single seam through which all privileged subprocess invocation
    flows. Injected via ``OpContext`` (and threaded into reconcile) so ops
    are testable without monkeypatching module globals: a test passes a
    recording fake and asserts on final state, not call order.
    """

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = ...,
        stdin_data: bytes | None = ...,
        extra_env: dict[str, str] | None = ...,
        check: bool = ...,
    ) -> CommandResult: ...

    def resolve(self, name: str) -> str | None:
        """Absolute path of ``name`` iff present and on the allow-list."""
        ...


class RealExec:
    """Production ``Exec``: delegates to this module's functions."""

    def run(
        self,
        argv: list[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        stdin_data: bytes | None = None,
        extra_env: dict[str, str] | None = None,
        check: bool = False,
    ) -> CommandResult:
        return run(
            argv,
            timeout=timeout,
            stdin_data=stdin_data,
            extra_env=extra_env,
            check=check,
        )

    def resolve(self, name: str) -> str | None:
        return resolve_allowed_binary(name)


#: Shared production instance. Tests inject their own ``Exec``.
DEFAULT_EXEC: Exec = RealExec()
