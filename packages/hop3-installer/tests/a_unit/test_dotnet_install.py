# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Install the long-term .NET SDKs a platform publishes, and fail loud otherwise.

No feed publishes both SDKs for every platform (Debian 12 on arm64 has no 8,
Ubuntu 22.04 on arm64 no 10), so one that is not published is named and
skipped; one that is published and fails to install aborts, as does a
platform with neither. SDK 9 used to be installed too: no feed carries it for
Ubuntu 24.04, and every such install printed a warning and went on.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hop3_installer.common import CommandError
from hop3_installer.server_installer import deps_common


def _install(monkeypatch, *, offered: set[str], failing: str = "") -> list[str]:
    installed: list[str] = []

    def fake_run(cmd, **_kw):
        pkg = cmd[-1]
        if pkg == failing:
            return SimpleNamespace(returncode=100, stdout="E: broken", stderr="")
        installed.append(pkg)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deps_common, "run_cmd", fake_run)
    deps_common._install_dotnet_sdks(
        is_offered=lambda pkg: pkg in offered,
        install_cmd=lambda pkg: ["install", pkg],
    )
    return installed


def test_every_published_lts_sdk_is_installed(monkeypatch):
    installed = _install(monkeypatch, offered={"dotnet-sdk-8.0", "dotnet-sdk-10.0"})

    assert installed == ["dotnet-sdk-8.0", "dotnet-sdk-10.0"]


def test_an_sdk_the_platform_lacks_is_skipped(monkeypatch):
    assert _install(monkeypatch, offered={"dotnet-sdk-10.0"}) == ["dotnet-sdk-10.0"]


def test_a_platform_with_no_sdk_aborts(monkeypatch):
    with pytest.raises(CommandError):
        _install(monkeypatch, offered=set())


def test_a_published_sdk_that_fails_to_install_aborts(monkeypatch):
    with pytest.raises(CommandError):
        _install(
            monkeypatch,
            offered={"dotnet-sdk-8.0", "dotnet-sdk-10.0"},
            failing="dotnet-sdk-10.0",
        )


@pytest.mark.parametrize(
    ("policy", "offered"),
    [
        ("dotnet-sdk-8.0:\n  Installed: (none)\n  Candidate: 8.0.131-0ubuntu1\n", True),
        ("dotnet-sdk-9.0:\n  Installed: (none)\n  Candidate: (none)\n", False),
        ("", False),  # apt knows nothing of the package
    ],
)
def test_apt_offers_reads_the_install_candidate(monkeypatch, policy, offered):
    monkeypatch.setattr(
        deps_common,
        "run_cmd",
        lambda cmd, **_kw: SimpleNamespace(returncode=0, stdout=policy, stderr=""),
    )

    assert deps_common._apt_offers("dotnet-sdk-8.0") is offered
