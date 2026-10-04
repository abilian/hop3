# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A server deploy that carried past a warning fails the run.

Two bugs in the deployer's CLI step and a .NET install failing on every
Ubuntu 24.04 server hid for weeks behind ⚠ lines every run log carried and
nobody read. A review does not reliably catch a new warning-and-continue; a
failed run does. See notes/installer-fail-loud-audit.md.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hop3_testing.targets import helpers

_WARN = "      \x1b[33m⚠\x1b[0m "


def _deploy(monkeypatch, transcript: str, **kwargs) -> bool:
    monkeypatch.setattr(
        helpers,
        "run_streaming",
        lambda *_a, **_kw: SimpleNamespace(
            returncode=0, timed_out=False, stdout=transcript, stderr=""
        ),
    )
    ok, _ = helpers.run_hop3_deploy(docker=True, **kwargs)
    return ok


def test_a_clean_deploy_passes(monkeypatch):
    assert _deploy(monkeypatch, "  ✓ Services started\nDeployment complete!\n")


def test_a_deploy_that_carried_past_a_warning_fails(monkeypatch, capsys):
    transcript = f"{_WARN}.NET SDK 9 installation failed\nDeployment complete!\n"

    assert not _deploy(monkeypatch, transcript)
    assert ".NET SDK 9 installation failed" in capsys.readouterr().out


def test_a_justified_warning_passes(monkeypatch):
    transcript = f"{_WARN}no cgroup v2 unified hierarchy at /sys/fs/cgroup\n"
    assert _deploy(monkeypatch, transcript)


def test_an_old_checkouts_deployer_is_not_gated(monkeypatch, tmp_path):
    """The upgrade chain runs a previous release's deployer from its worktree."""
    transcript = f"{_WARN}Failed to start Docker daemon\n"
    assert _deploy(monkeypatch, transcript, cwd=tmp_path)


@pytest.mark.parametrize(
    "line",
    [
        "nft not found on PATH; skipping inet hop3 table creation",
        "Could not write build info: [Errno 13] Permission denied",
        "Could not add Microsoft's repository from https://packages.microsoft.com/x",
    ],
)
def test_every_allowlisted_warning_matches_its_installer_text(line):
    assert helpers.untolerated_deploy_warnings(f"{_WARN}{line}") == []
