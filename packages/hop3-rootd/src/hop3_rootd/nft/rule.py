# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, EM102, TC001

"""nftables rule construction and emission.

Each PortSpec maps to a single `nft add rule …` invocation in the
`inet hop3 input` chain. The rule carries a comment of the form
`hop3:rule:<rule_id>` so we can identify and remove it later.

See ADR 041 §6 and `local-notes/plans/firewall.md` §5 for the rule shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from hop3_rootd.exec import (
    CommandResult,
    InvalidBinaryError,
    resolve_allowed_binary,
    run as exec_run,
)
from hop3_rootd.validation import PortSpec

# --- Constants -------------------------------------------------------------

TABLE_FAMILY: Final[str] = "inet"
TABLE_NAME: Final[str] = "hop3"
CHAIN_NAME: Final[str] = "input"

COMMENT_PREFIX: Final[str] = "hop3:rule:"


# --- Errors ----------------------------------------------------------------


class NftError(Exception):
    """Base class for nftables-level errors."""


class NftBinaryNotFoundError(NftError):
    """nft is not present on this system or not in the allow-list."""


class NftCommandError(NftError):
    """An nft invocation failed (returncode != 0)."""

    def __init__(self, argv: list[str], returncode: int, stderr: str):
        super().__init__(
            f"nft command failed (rc={returncode}): {' '.join(argv)}\n  stderr: {stderr}"
        )
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr


# --- nft path resolution --------------------------------------------------


def find_nft_binary() -> str:
    """Return the absolute path to nft, or raise NftBinaryNotFoundError.

    Wraps `resolve_allowed_binary` to keep the nft-specific error message.
    """
    path = resolve_allowed_binary("nft")
    if path is None:
        raise NftBinaryNotFoundError(
            "nft binary not found on PATH or not on the exec allow-list"
        )
    return path


# --- Rule comment helpers --------------------------------------------------


def make_comment(rule_id: str) -> str:
    """The comment string that tags a rule as rootd-managed."""
    return f"{COMMENT_PREFIX}{rule_id}"


def parse_comment(comment: str | None) -> str | None:
    """Inverse of make_comment: extract rule_id from a rule comment, or None.

    Returns None for non-rootd comments (or absence). Used during reconcile
    to map kernel rules back to rootd's stored rule_ids.
    """
    if comment is None or not comment.startswith(COMMENT_PREFIX):
        return None
    return comment[len(COMMENT_PREFIX) :]


# --- Building the nft argv -------------------------------------------------


def build_add_argv(spec: PortSpec, rule_id: str) -> list[str]:
    """Construct the `nft add rule …` argv for a PortSpec.

    The rule layout:

      [<saddr-clause>] <protocol> dport <port-or-range> accept comment "<id>"

    saddr clause is omitted when source == "any". Otherwise:
      ip saddr <cidr>     for IPv4
    """
    nft = find_nft_binary()
    argv: list[str] = [
        nft,
        "add",
        "rule",
        TABLE_FAMILY,
        TABLE_NAME,
        CHAIN_NAME,
    ]

    # Source filter (IPv4 only in v1; IPv6 destinations are auto-handled
    # by the inet family but source filtering is rejected upstream).
    if spec.source != "any":
        argv += ["ip", "saddr", spec.source]

    # Protocol + dport.
    argv += [spec.protocol, "dport", _format_port_or_range(spec)]

    # Verdict + comment marker.
    argv += ["accept", "comment", make_comment(rule_id)]
    return argv


def _format_port_or_range(spec: PortSpec) -> str:
    """Render the dport argument as a single nft token."""
    if spec.port is not None:
        return str(spec.port)
    if spec.port_range is not None:
        start, end = spec.port_range
        return f"{start}-{end}"
    raise ValueError("PortSpec has neither port nor port_range — should be unreachable")


def build_delete_argv(handle: int) -> list[str]:
    """Construct `nft delete rule … handle <N>`.

    Deletion in nftables is by handle, not by content. Handles are
    returned in the JSON output of `nft -j list table …` and are stable
    until the next ruleset reload (which we don't trigger).
    """
    nft = find_nft_binary()
    return [
        nft,
        "delete",
        "rule",
        TABLE_FAMILY,
        TABLE_NAME,
        CHAIN_NAME,
        "handle",
        str(handle),
    ]


# --- Running nft commands -------------------------------------------------


def run_nft(argv: list[str], *, timeout: float = 10.0) -> CommandResult:
    """Run an nft command, raising NftCommandError on non-zero exit."""
    try:
        result = exec_run(argv, timeout=timeout)
    except InvalidBinaryError as e:
        raise NftBinaryNotFoundError(str(e)) from e
    if not result.success:
        raise NftCommandError(argv, result.returncode, result.stderr)
    return result


# --- Parsing nft -j list output -------------------------------------------


@dataclass(frozen=True)
class KernelRule:
    """One rule as read from `nft -j list table inet hop3` output.

    Only the fields we need for reconciliation. The full nft JSON has
    much more; we ignore everything else.
    """

    handle: int
    comment: str | None
    raw: dict[str, Any]  # the full original rule block, for diagnostics


def parse_list_output(json_obj: dict[str, Any]) -> list[KernelRule]:
    """Extract the list of rules from `nft -j list table inet hop3` output.

    Input shape (relevant pieces):

        {"nftables": [
            {"table": {...}},
            {"chain": {...}},
            {"rule": {"family": "inet", "table": "hop3", "chain": "input",
                      "handle": 4, "expr": [...], "comment": "hop3:rule:..."}}
        ]}

    Non-rule entries (table, chain) are ignored. Rules without a `handle`
    are ignored too (shouldn't happen but be safe).
    """
    items = json_obj.get("nftables", [])
    if not isinstance(items, list):
        raise NftError(
            f"nft output 'nftables' should be list, got {type(items).__name__}"
        )

    rules: list[KernelRule] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule")
        if not isinstance(rule, dict):
            continue
        handle = rule.get("handle")
        if not isinstance(handle, int):
            continue  # skip malformed
        comment = rule.get("comment") if isinstance(rule.get("comment"), str) else None
        rules.append(KernelRule(handle=handle, comment=comment, raw=rule))
    return rules
