# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, EM102, TC001

"""Firewall ops: add_rule, remove_rule, list_rules.

Each op handler:
  - validates args (raises ValidationError on bad input)
  - performs the nft mutation (raises NftCommandError on kernel failure)
  - updates state.json via ctx.save_state()
  - returns the typed result

Atomicity: state-first, apply-second, rollback on failure (ADR 041 §7).
"""

from __future__ import annotations

from typing import Any

from hop3_rootd.exec import DEFAULT_EXEC, Exec
from hop3_rootd.nft.rule import (
    NftCommandError,
    build_add_argv,
    build_delete_argv,
    parse_comment,
    run_nft,
)
from hop3_rootd.nft.table import list_rules as nft_list_rules
from hop3_rootd.ops._base import OpContext, StateConflictError, register
from hop3_rootd.protocol import Request
from hop3_rootd.state import StoredRule
from hop3_rootd.validation import (
    ValidationError,
    validate_app_name,
    validate_port_spec,
)

# --- firewall.add_rule ---------------------------------------------------


@register("firewall.add_rule")
def add_rule(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Add one rule to the inet hop3 input chain.

    Apply via nft first; persist to state.json on success. A crash
    between nft success and state persist leaves the rule in the kernel
    without a state row — reconcile.py removes that case as an orphan.
    A crash before nft success leaves no trace. Either way, no fsync is
    spent on a transient "pending" status that isn't observed externally.
    """
    spec = validate_port_spec(req.args)
    rule_id = ctx.new_rule_id()
    applied_at = ctx.now_iso()
    spec_dict = _spec_to_dict(spec)

    argv = build_add_argv(spec, rule_id=rule_id, exec=ctx.exec)
    run_nft(argv, exec=ctx.exec)
    nft_handle = _resolve_handle_for_rule_id(rule_id, exec=ctx.exec)

    ctx.state.rules.append(
        StoredRule(
            rule_id=rule_id,
            spec=spec_dict,
            applied_at=applied_at,
            status="applied",
        )
    )
    ctx.save_state()

    return {
        "rule_id": rule_id,
        "spec": spec_dict,
        "applied_at": applied_at,
        "nft_handle": nft_handle,
        "table": "inet hop3",
    }


# --- firewall.remove_rule ------------------------------------------------


@register("firewall.remove_rule")
def remove_rule(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Remove a rule by rootd's stable rule_id.

    Returns:
        {"removed": True, "rule_id": "..."}

    Raises StateConflictError if no rule with that id is in state.
    """
    rule_id = req.args.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValidationError("rule_id", "must be a non-empty string")

    stored = ctx.state.find_rule(rule_id)
    if stored is None:
        raise StateConflictError(f"rule_id {rule_id!r} not found in state")

    handle = _resolve_handle_for_rule_id(rule_id, exec=ctx.exec)
    if handle is None:
        # State has it, kernel doesn't. Drop from state and report.
        ctx.state.rules = [r for r in ctx.state.rules if r.rule_id != rule_id]
        ctx.save_state()
        return {"removed": True, "rule_id": rule_id, "kernel_state": "absent"}

    # Run delete first; persist on success. A crash between nft delete
    # and state persist leaves a stale row in state — reconcile re-applies
    # at next start, which is the safe direction (rule reappears rather
    # than silently disappearing).
    run_nft(build_delete_argv(handle, exec=ctx.exec), exec=ctx.exec)
    ctx.state.rules = [r for r in ctx.state.rules if r.rule_id != rule_id]
    ctx.save_state()
    return {"removed": True, "rule_id": rule_id}


# --- firewall.list_rules -------------------------------------------------


@register("firewall.list_rules", audit=False)
def list_rules(req: Request, ctx: OpContext) -> dict[str, Any]:
    """List rules currently in state. Optionally filter by app_name.

    Returns:
        {"rules": [<StoredRule serialised>, ...]}
    """
    app_filter = req.args.get("app_name")
    if app_filter is not None:
        # Validate the filter format (defense in depth).
        validate_app_name(app_filter)
        rules = ctx.state.rules_for_app(app_filter)
    else:
        rules = list(ctx.state.rules)

    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "spec": r.spec,
                "applied_at": r.applied_at,
                "status": r.status,
            }
            for r in rules
        ]
    }


# --- Helpers --------------------------------------------------------------


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialise a PortSpec to a plain dict for state.json / response."""
    out: dict[str, Any] = {
        "protocol": spec.protocol,
        "app_name": spec.app_name,
        "source": spec.source,
    }
    if spec.port is not None:
        out["port"] = spec.port
    if spec.port_range is not None:
        out["port_range"] = list(spec.port_range)
    if spec.description is not None:
        out["description"] = spec.description
    return out


def _resolve_handle_for_rule_id(
    rule_id: str, *, exec: Exec = DEFAULT_EXEC
) -> int | None:
    """Find the nftables `handle` of the kernel rule whose comment matches.

    Returns None if no such rule is in the kernel right now (e.g., the rule
    was removed out-of-band, or hasn't been applied yet).
    """
    try:
        kernel_rules = nft_list_rules(exec=exec)
    except NftCommandError:
        # If list fails (e.g., table doesn't exist), surface that as "no
        # match". add_rule's caller will see the error from its own nft
        # invocation; remove_rule's caller has already mutated state.
        return None

    for kr in kernel_rules:
        if parse_comment(kr.comment) == rule_id:
            return kr.handle
    return None
