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
from unittest.mock import patch

import pytest
from hop3_installer.common import CommandError, InstallStepError
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
    with pytest.raises(InstallStepError):
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


def test_an_installed_sdk_counts_as_offered_on_fedora():
    """`dnf list --available` may omit it, and a redeploy then aborted."""
    answers = {"rpm": 0, "dnf": 1}

    def run(cmd, **_kw):
        return SimpleNamespace(returncode=answers[cmd[0]], stdout="", stderr="")

    with patch.object(deps_common, "run_cmd", side_effect=run):
        assert deps_common._dnf_offers("dotnet-sdk-10.0")


def test_debian_without_microsofts_repository_stops_the_install():
    """Debian has no .NET of its own: nothing could be installed after it."""
    with (
        patch.object(
            deps_common, "_detect_debian_version", return_value=("debian", "12")
        ),
        patch.object(deps_common, "_add_microsoft_repository", return_value=False),
        pytest.raises(InstallStepError, match=r"Debian has no \.NET packages"),
    ):
        deps_common.install_dotnet_sdk_debian()


def test_on_ubuntu_a_missing_sdk_names_the_repository_failure(capsys):
    """It said "not published" when the repository had failed to be added."""
    with (
        patch.object(
            deps_common, "_detect_debian_version", return_value=("ubuntu", "24.04")
        ),
        patch.object(deps_common, "_add_microsoft_repository", return_value=False),
        patch.object(
            deps_common,
            "run_cmd",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ),
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "_apt_offers", lambda pkg: pkg.endswith("8.0")),
    ):
        deps_common.install_dotnet_sdk_debian()

    assert "Microsoft's repository could not be added" in capsys.readouterr().out
