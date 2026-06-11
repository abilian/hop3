# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared on-failure SUT diagnostics — make every failure self-diagnosing.

A tutorial/demo failure used to be a black box ("Command timed out after 120s"
and nothing else). collect_failure_diagnostics always snapshots `hop3 apps`
(name-independent — reveals an app stuck mid-build, or a stranded one holding a
port) and, when an app name is known, adds runtime logs + the diagnostic bundle.
It must never raise — diagnostics must not crash the run.
"""

from __future__ import annotations

from hop3_testing.runners._diagnostics import (
    collect_failure_diagnostics,
    hop3_apps_snapshot,
    target_kind,
)


class _Target:
    def __init__(self, apps=(0, "", ""), raises=False):
        self._apps = apps
        self._raises = raises

    def exec_run(self, _cmd):
        if self._raises:
            msg = "ssh down"
            raise RuntimeError(msg)
        return self._apps


class _RemoteTarget(_Target):
    pass


def _boom(*_a, **_k):
    msg = "boom"
    raise RuntimeError(msg)


def test_target_kind():
    assert target_kind(_Target()) == "docker"
    assert target_kind(_RemoteTarget()) == "ssh"


def test_apps_snapshot_included_and_labelled():
    snap = hop3_apps_snapshot(_Target(apps=(0, "fiber BUILDING\ngin RUNNING", "")))
    assert "hop3 apps" in snap
    assert "fiber BUILDING" in snap


def test_apps_snapshot_empty_when_exec_raises():
    assert hop3_apps_snapshot(_Target(raises=True)) == ""


def test_collect_without_app_name_is_apps_snapshot_only():
    logs, bundle = collect_failure_diagnostics(
        _Target(apps=(0, "fiber BUILDING", "")), None, deploy_logs="x"
    )
    assert "fiber BUILDING" in logs  # the leftover/mid-build detector
    assert bundle is None  # no per-app bundle without a name


def test_collect_with_app_name_adds_runtime_logs_and_bundle(monkeypatch):
    monkeypatch.setattr(
        "hop3_testing.runners._diagnostics.collect_runtime_logs",
        lambda _t, name: f"runtime logs for {name}",
    )
    monkeypatch.setattr(
        "hop3_testing.runners._diagnostics.collect_diagnostic_bundle",
        lambda *a, **k: "BUNDLE",
    )
    logs, bundle = collect_failure_diagnostics(
        _Target(apps=(0, "ghost RUNNING", "")), "ghost", deploy_logs="x"
    )
    assert "ghost RUNNING" in logs
    assert "runtime logs for ghost" in logs
    assert bundle == "BUNDLE"


def test_collect_never_raises_even_if_collectors_explode(monkeypatch):
    monkeypatch.setattr("hop3_testing.runners._diagnostics.collect_runtime_logs", _boom)
    monkeypatch.setattr(
        "hop3_testing.runners._diagnostics.collect_diagnostic_bundle", _boom
    )
    logs, bundle = collect_failure_diagnostics(_Target(apps=(0, "ghost", "")), "ghost")
    assert "ghost" in logs  # apps snapshot still present
    assert bundle is None  # bundle collection swallowed
