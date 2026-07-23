# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
Op protocol and registry.

An "op" is a typed-intent handler invoked by the server's dispatcher.
Each op:
  - takes a `Request` (parsed envelope) and an `OpContext` (state, deps)
  - validates its `args` (raising ValidationError on failure)
  - performs its side-effect (nft, nginx, none)
  - returns either a result dict (success) or raises an exception

Exceptions the dispatcher catches:
  - ValidationError                → validation_failed
  - NftCommandError / NftError     → kernel_error
  - StateConflictError             → state_conflict
  - any other Exception            → internal_error (with full traceback logged)

Ops never write audit logs themselves — the dispatcher does that around
each invocation, with the request id and duration captured.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from hop3_rootd.exec import DEFAULT_EXEC, Exec
from hop3_rootd.protocol import Request

if TYPE_CHECKING:
    # cycle-free: state.py imports nothing from ops
    from hop3_rootd.state import State

# --- Errors --------------------------------------------------------------


class StateConflictError(Exception):
    """
    Raised by an op when the requested state change conflicts with current state.

    Examples:
      - remove_rule for a rule_id that doesn't exist
      - add_rule for a (port, protocol, source) that's already present
        (we don't enforce port uniqueness yet, but the slot is here)
    """


# --- DaemonStats: mutable runtime metrics surfaced via daemon.health ----


@dataclass
class DaemonStats:
    """
    Runtime statistics for the daemon. Owned by the Server and passed
    to ops via `OpContext.stats`. Replaces the previous module-level
    globals in ``ops/daemon.py``.

    Single-threaded read/write today (single accept loop, sequential
    dispatch). If the server ever grows worker threads, the increment
    in `increment_error()` becomes an unsynchronised RMW and needs a
    lock.
    """

    started_at: float = field(default_factory=time.time)
    last_request_at: float = field(default_factory=time.time)
    last_reconcile_at: str | None = None
    errors_last_hour: int = 0

    def mark_request(self) -> None:
        self.last_request_at = time.time()

    def mark_reconcile(self, iso: str) -> None:
        self.last_reconcile_at = iso

    def increment_error(self) -> None:
        self.errors_last_hour += 1

    def reset_errors(self) -> None:
        self.errors_last_hour = 0


# --- OpContext: shared dependencies passed to every op ------------------


@dataclass
class OpContext:
    """
    Bundle of dependencies the dispatcher passes to each op handler.

    Carrying these as a context object (rather than module globals) makes
    ops directly testable: pass a fake state, a fake clock, etc.
    """

    state: State
    save_state: Callable[[], None]  # persists the current state to state.json
    now_iso: Callable[[], str]  # returns current UTC time as ISO-8601 string
    new_rule_id: Callable[[], str]  # returns a fresh rule_id (UUID4 string)
    stats: DaemonStats = field(default_factory=DaemonStats)
    exec: Exec = DEFAULT_EXEC  # subprocess seam; tests inject a recording fake


# --- Op protocol --------------------------------------------------------


class OpHandler(Protocol):
    """Each registered op implements this signature."""

    def __call__(self, req: Request, ctx: OpContext, /) -> dict[str, Any]:
        """
        Execute the op. Return the success-result dict.

        Args are positional-only so implementations may rename them
        (e.g. `_req`, `_ctx`) without breaking type checks.

        Raise ValidationError, StateConflictError, NftError, or other
        Exception on failure — the dispatcher converts to a Response.
        """
        ...


# --- Registry -----------------------------------------------------------


@dataclass(frozen=True)
class OpRegistration:
    """Metadata stored alongside an op handler in the registry."""

    handler: OpHandler
    audit: bool  # whether to write an audit log entry on each invocation


_REGISTRY: dict[str, OpRegistration] = {}


def register(op_name: str, *, audit: bool = True) -> Callable[[OpHandler], OpHandler]:
    """
    Decorator: register an op handler under its dotted name.

    `audit=False` skips the audit log for this op — used for read-only
    ops (daemon.health, daemon.handshake, list/query ops) that would
    otherwise drown the log under polling traffic. The journald
    operational log still captures errors for these.
    """

    def decorator(fn: OpHandler) -> OpHandler:
        if op_name in _REGISTRY:
            raise ValueError(f"op {op_name!r} already registered")
        _REGISTRY[op_name] = OpRegistration(handler=fn, audit=audit)
        return fn

    return decorator


def get_handler(op_name: str) -> OpHandler | None:
    """Return the registered handler for `op_name`, or None if not found."""
    reg = _REGISTRY.get(op_name)
    return reg.handler if reg is not None else None


def get_registration(op_name: str) -> OpRegistration | None:
    """Return the full registration record (handler + metadata)."""
    return _REGISTRY.get(op_name)


def all_ops() -> list[str]:
    """Return the list of registered op names. For diagnostics / health."""
    return sorted(_REGISTRY.keys())
