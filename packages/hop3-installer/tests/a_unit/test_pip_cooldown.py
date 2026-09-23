# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The server venv's supply-chain cooldown.

pip in the server venv takes no distribution uploaded in the last week, except
Hop3's own packages, which would otherwise be uninstallable for a week after
every release.
"""

from __future__ import annotations

import configparser

import pytest
from hop3_installer.server_installer import python as mod


@pytest.fixture
def calls(monkeypatch) -> list[tuple[list[str], bool]]:
    recorded: list[tuple[list[str], bool]] = []

    def fake_run_as_hop3(argv, *, check=False, timeout=None):
        recorded.append((list(argv), check))

    monkeypatch.setattr(mod, "run_as_hop3", fake_run_as_hop3)
    return recorded


def test_the_venv_config_carries_the_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "VENV_DIR", tmp_path)
    monkeypatch.setattr(mod, "_chown_hop3", lambda path: None)

    mod.write_pip_cooldown()

    conf = configparser.ConfigParser()
    conf.read(tmp_path / "pip.conf")
    assert conf["install"]["uploaded-prior-to"] == mod.DEPENDENCY_COOLDOWN


def test_our_own_package_goes_in_uncooled_and_alone(calls):
    mod._pip_install_own("pip", "hop3-server[waf]==0.7.5", "--pre")

    (first, first_checked), (second, second_checked) = calls
    assert first == [
        "pip",
        "install",
        "--pre",
        "--no-deps",
        "--uploaded-prior-to=P0D",
        "hop3-server[waf]==0.7.5",
    ]
    # The dependencies resolve under the venv's cutoff: nothing lifts it here.
    assert second == ["pip", "install", "--pre", "hop3-server[waf]==0.7.5"]
    assert first_checked
    assert second_checked
