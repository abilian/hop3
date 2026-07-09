# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the daemon startup sequence (hop3_rootd.__main__).

Regression focus: a host without the nft firewall backend (e.g. a container,
or a restricted VPS) must still be able to run hop3-rootd for its proxy /
process duties. The daemon used to treat *any* reconciliation failure —
including "nft binary not found" — as fatal, so it never bound its socket and
nginx/proxy operations were impossible. See the demo01 deploy failure where
the redeploy's proxy setup reported "hop3-rootd socket not found".
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from hop3_rootd import __main__ as main_mod
from hop3_rootd.nft.rule import NftBinaryNotFoundError, NftError
from hop3_rootd.state import State, init_empty

if TYPE_CHECKING:
    from pathlib import Path


def _argv(tmp_path: Path, state_path: Path) -> list[str]:
    return [
        "--state-path",
        str(state_path),
        "--socket-path",
        str(tmp_path / "sock"),
        "--audit-log",
        str(tmp_path / "audit.log"),
    ]


def test_main_starts_when_nft_missing_and_no_rules(tmp_path: Path) -> None:
    """Missing nft + empty state → skip firewall reconciliation, serve anyway."""
    state_path = tmp_path / "state.json"
    init_empty(state_path)  # 0 rules

    fake_server = MagicMock()
    fake_server.inherit_systemd_socket.return_value = True  # skip bind()
    fake_server.run.return_value = None

    with (
        patch.object(
            main_mod,
            "reconcile",
            side_effect=NftBinaryNotFoundError("nft binary not found"),
        ),
        patch.object(main_mod, "Server", return_value=fake_server),
        patch.object(main_mod, "AuditLog", return_value=MagicMock()),
        patch.object(main_mod, "save") as mock_save,
    ):
        rc = main_mod.main(_argv(tmp_path, state_path))

    assert rc == main_mod.EXIT_OK
    # The daemon went on to serve its socket rather than crashing.
    fake_server.run.assert_called_once()
    # Reconciliation was skipped, so state.json was not re-written.
    mock_save.assert_not_called()


def test_main_refuses_when_reconcile_fails_for_other_reasons(tmp_path: Path) -> None:
    """nft present but the kernel call fails → stays fatal (ADR 041 §6).

    Only an *absent* firewall backend is tolerated; a genuine kernel-
    interaction fault still refuses to start so a broken firewall is loud.
    """
    state_path = tmp_path / "state.json"
    init_empty(state_path)

    with (
        patch.object(main_mod, "reconcile", side_effect=NftError("kernel unreachable")),
        patch.object(main_mod, "Server") as mock_server,
    ):
        rc = main_mod.main(_argv(tmp_path, state_path))

    assert rc == main_mod.EXIT_RECONCILE_ERROR
    # Never reached the serving stage.
    mock_server.assert_not_called()


# --- _try_reconcile (the non-fatal reconcile degrade-policy helper) -------


def test_try_reconcile_returns_report_on_success() -> None:
    """On success the report is handed back so the caller can persist + log it."""
    sentinel = object()
    report = main_mod._try_reconcile(
        State(),
        lambda _state: sentinel,
        noun="x",
        tracked=0,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is sentinel


def test_try_reconcile_degrades_on_unavailable() -> None:
    """An unavailable backend → None (caller skips persist); logged, not raised."""

    def raise_unavail(_state: State) -> object:
        raise RuntimeError  # stands in for CgroupUnavailableError etc.

    report = main_mod._try_reconcile(
        State(),
        raise_unavail,
        noun="x",
        tracked=2,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is None


def test_try_reconcile_degrades_on_error() -> None:
    """A non-unavailable error → None (degrade), not a crash."""

    def raise_err(_state: State) -> object:
        raise ValueError  # stands in for a per-item reconcile error

    report = main_mod._try_reconcile(
        State(),
        raise_err,
        noun="x",
        tracked=0,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is None
