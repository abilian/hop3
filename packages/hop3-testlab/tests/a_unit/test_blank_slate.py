# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Blank-slate rebuild: full-suite runs reinstall the Hetzner OS first.

Reproducibility: every run starts from an identical, known state instead of
inheriting leaked apps/addons/disk. Requires a Hetzner ssh_key_name (re-injected
on rebuild) — without it we skip rather than lock ourselves out.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_testlab import worker
from hop3_testlab.cloud_config import CloudConfig


def _cfg(ssh_key_name: str | None) -> CloudConfig:
    return CloudConfig(
        hetzner_token="tok",
        hetzner_server_id=42,
        hetzner_image="ubuntu-24.04",
        ssh_key_path=None,
        hetzner_ssh_key_name=ssh_key_name,
    )


def test_rebuild_skipped_without_ssh_key_name(capsys):
    with patch("hop3_testing.system_tests.hetzner.HetznerManager") as manager_cls:
        worker._rebuild_blank_slate(_cfg(None))
    manager_cls.assert_not_called()  # never rebuild without a key (would lock us out)
    assert "SKIPPED" in capsys.readouterr().out


def test_rebuild_runs_and_waits_when_key_configured():
    manager = MagicMock()
    manager.wait_for_ssh_ready.return_value = True
    with patch(
        "hop3_testing.system_tests.hetzner.HetznerManager", return_value=manager
    ):
        worker._rebuild_blank_slate(_cfg("hop3-ci"))
    manager.rebuild_server.assert_called_once()
    manager.wait_for_ssh_ready.assert_called_once()


def test_rebuild_raises_if_ssh_never_ready():
    manager = MagicMock()
    manager.wait_for_ssh_ready.return_value = False
    with (
        patch("hop3_testing.system_tests.hetzner.HetznerManager", return_value=manager),
        pytest.raises(RuntimeError),
    ):
        worker._rebuild_blank_slate(_cfg("hop3-ci"))


def _wire(monkeypatch, calls):
    monkeypatch.setattr(worker, "_resolve_run_target", lambda t: ("1.2.3.4", None, {}))
    monkeypatch.setattr(worker, "load_cloud_config", lambda: _cfg("hop3-ci"))
    monkeypatch.setattr(
        worker, "_rebuild_blank_slate", lambda cfg: calls.append("rebuild")
    )
    monkeypatch.setattr(worker, "_run_engine", lambda *a, **k: calls.append("engine"))


def test_full_suite_hetzner_run_rebuilds_first(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor("hetzner", "nightly", apps=None)
    assert calls == ["rebuild", "engine"]  # blank slate, then run


def test_per_app_rerun_skips_rebuild(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor("hetzner", "nightly", apps=["apps/real-apps-docker/x"])
    assert calls == ["engine"]  # quick re-run against the live server


def test_other_ssh_host_does_not_rebuild(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    worker._default_executor("box.example.com", "nightly", apps=None)
    assert calls == ["engine"]  # only the managed "hetzner" target is rebuilt


def test_docker_target_does_not_rebuild(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        worker, "_rebuild_blank_slate", lambda cfg: calls.append("rebuild")
    )
    monkeypatch.setattr(worker, "_run_engine", lambda *a, **k: calls.append("engine"))
    worker._default_executor("docker", "nightly", apps=None)
    assert "rebuild" not in calls
