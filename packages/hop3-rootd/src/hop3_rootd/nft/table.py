# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM102

"""nftables table management.

Rootd owns the `inet hop3` table exclusively. This module handles:
  - ensuring the table+chain exist (idempotent; called at startup)
  - querying the current rule list via `nft -j list table inet hop3`
  - removing the table on uninstall (driven by the installer, not the daemon)

Rules outside the `inet hop3` table are invisible to rootd — see ADR 041 §6
and the operator-contract principle in §6.
"""

from __future__ import annotations

import json
from typing import Final

from hop3_rootd.nft.rule import (
    CHAIN_NAME,
    TABLE_FAMILY,
    TABLE_NAME,
    KernelRule,
    NftCommandError,
    NftError,
    find_nft_binary,
    parse_list_output,
    run_nft,
)

# Strings emitted by nft when something doesn't exist. We use these to
# detect "already exists" / "not found" cases for idempotency.
_TABLE_EXISTS_MARKERS: Final[tuple[str, ...]] = (
    "File exists",
    "BUSY",
)


def ensure_table_exists() -> None:
    """Create the `inet hop3` table + `input` chain if absent. Idempotent.

    Safe to call multiple times. nft's behaviour:
      - `nft add table inet hop3` succeeds whether the table exists or not
        (modern nft is idempotent here; older versions returned EEXIST which
        we tolerate)
      - same for `nft add chain ...`
    """
    nft = find_nft_binary()

    # Create table.
    add_table = [nft, "add", "table", TABLE_FAMILY, TABLE_NAME]
    try:
        run_nft(add_table)
    except NftCommandError as e:
        if not _is_already_exists(e.stderr):
            raise

    # Create input chain with type=filter, hook=input, priority=filter (0),
    # policy=accept (additive — this chain only adds accept rules; deny is
    # the operator's main-chain responsibility).
    add_chain = [
        nft,
        "add",
        "chain",
        TABLE_FAMILY,
        TABLE_NAME,
        CHAIN_NAME,
        "{",
        "type",
        "filter",
        "hook",
        "input",
        "priority",
        "filter",
        ";",
        "policy",
        "accept",
        ";",
        "}",
    ]
    try:
        run_nft(add_chain)
    except NftCommandError as e:
        if not _is_already_exists(e.stderr):
            raise


def _is_already_exists(stderr: str) -> bool:
    """Tell whether an nft failure was actually a no-op idempotency case."""
    return any(marker in stderr for marker in _TABLE_EXISTS_MARKERS)


def list_rules() -> list[KernelRule]:
    """Return all rules currently in the `inet hop3 input` chain.

    Calls `nft -j list table inet hop3` and parses the JSON output.
    Returns an empty list if the table exists but has no rules.

    Raises NftError if nft fails or the output is malformed; callers
    should treat this as fatal and surface it (the daemon's reconcile
    loop refuses to start in that case).
    """
    nft = find_nft_binary()
    argv = [nft, "-j", "list", "table", TABLE_FAMILY, TABLE_NAME]
    result = run_nft(argv, timeout=5.0)

    try:
        obj = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise NftError(
            f"nft -j output is not valid JSON: {e}\n  stdout: {result.stdout[:500]}"
        ) from e

    if not isinstance(obj, dict):
        raise NftError(f"nft -j output should be object, got {type(obj).__name__}")

    return parse_list_output(obj)


def delete_table() -> None:
    """Remove the `inet hop3` table entirely.

    Called only on uninstall (ADR 041 §"Uninstall semantics"). The daemon
    itself never calls this on shutdown — `systemctl stop` preserves
    rules.
    """
    nft = find_nft_binary()
    argv = [nft, "delete", "table", TABLE_FAMILY, TABLE_NAME]
    try:
        run_nft(argv)
    except NftCommandError as e:
        # If the table doesn't exist, that's also success — nothing to do.
        if "No such file or directory" in e.stderr or "doesn't exist" in e.stderr:
            return
        raise
