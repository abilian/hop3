# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM102, TC001, TC003

"""Op protocol and registry.

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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from hop3_rootd.protocol import Request

# --- Errors --------------------------------------------------------------


class StateConflictError(Exception):
    """Raised by an op when the requested state change conflicts with current state.

    Examples:
      - remove_rule for a rule_id that doesn't exist
      - add_rule for a (port, protocol, source) that's already present
        (we don't enforce port uniqueness yet, but the slot is here)
    """


# --- OpContext: shared dependencies passed to every op ------------------


@dataclass
class OpContext:
    """Bundle of dependencies the dispatcher passes to each op handler.

    Carrying these as a context object (rather than module globals) makes
    ops directly testable: pass a fake state, a fake clock, etc.
    """

    state: Any  # hop3_rootd.state.State (kept Any to avoid circular import)
    state_path: Any  # Path to state.json; ops persist after mutations
    save_state: Callable[[], None]  # callable that persists the current state
    now_iso: Callable[[], str]  # returns current UTC time as ISO-8601 string
    new_rule_id: Callable[[], str]  # returns a fresh rule_id (UUID4 string)


# --- Op protocol --------------------------------------------------------


class OpHandler(Protocol):
    """Each registered op implements this signature."""

    def __call__(self, req: Request, ctx: OpContext) -> dict[str, Any]:
        """Execute the op. Return the success-result dict.

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
    """Decorator: register an op handler under its dotted name.

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


def clear_registry() -> None:
    """Reset the registry. Test-only."""
    _REGISTRY.clear()
