# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the daemon startup sequence (hop3_rootd.__main__).

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
from hop3_rootd.ops._base import DaemonStats
from hop3_rootd.state import State, StoredRule, init_empty, load, save

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
    """
    nft present but the kernel call fails → stays fatal (ADR 041 §6).

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
    report, outcome = main_mod._try_reconcile(
        State(),
        lambda _state: sentinel,
        noun="x",
        tracked=0,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is sentinel
    assert outcome["status"] == "ok"


def test_try_reconcile_degrades_on_unavailable() -> None:
    """An unavailable backend → None (caller skips persist); logged, not raised."""

    def raise_unavail(_state: State) -> object:
        msg = "no cgroup2"
        raise RuntimeError(msg)  # stands in for CgroupUnavailableError

    report, outcome = main_mod._try_reconcile(
        State(),
        raise_unavail,
        noun="x",
        tracked=2,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is None
    assert outcome == {"status": "unavailable", "detail": "no cgroup2", "tracked": 2}


def test_try_reconcile_degrades_on_error() -> None:
    """A non-unavailable error → None (degrade), not a crash."""

    def raise_err(_state: State) -> object:
        msg = "leaf busy"
        raise ValueError(msg)  # stands in for a per-item reconcile error

    report, outcome = main_mod._try_reconcile(
        State(),
        raise_err,
        noun="x",
        tracked=0,
        unavailable_exc=RuntimeError,
        error_exc=ValueError,
    )
    assert report is None
    assert outcome == {"status": "error", "detail": "leaf busy", "tracked": 0}


def test_main_records_each_reconcile_outcome_in_stats(tmp_path: Path) -> None:
    """
    A degraded startup reaches daemon.health, not only the journal.

    nft missing while rules are stored leaves the firewall unenforced: the
    outcome is recorded on the server's stats, and health names it degraded.
    """
    state_path = tmp_path / "state.json"
    init_empty(state_path)
    state = load(state_path)
    state.rules.append(StoredRule("r1", {}, "2026-04-24T00:00:00Z"))
    save(state, state_path)

    fake_server = MagicMock()
    fake_server.inherit_systemd_socket.return_value = True
    fake_server.stats = DaemonStats()

    with (
        patch.object(
            main_mod, "reconcile", side_effect=NftBinaryNotFoundError("no nft")
        ),
        patch.object(main_mod, "Server", return_value=fake_server),
        patch.object(main_mod, "AuditLog", return_value=MagicMock()),
        patch.object(main_mod, "_startup_reconcile_cgroups", return_value=_SKIP),
        patch.object(main_mod, "_startup_reconcile_mounts", return_value=_SKIP),
        patch.object(main_mod, "_startup_reconcile_proxies", return_value=_SKIP),
    ):
        assert main_mod.main(_argv(tmp_path, state_path)) == main_mod.EXIT_OK

    stats = fake_server.stats
    assert stats.reconcile["firewall"] == {
        "status": "unavailable",
        "detail": "no nft",
        "tracked": 1,
    }
    assert stats.reconcile["mounts"]["status"] == "skipped"
    assert stats.degraded_subsystems() == ["firewall"]


_SKIP = {"status": "skipped", "detail": "nothing tracked", "tracked": 0}
