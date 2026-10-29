# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""OS setup starts the services it enables, and only under systemd."""

from __future__ import annotations

import pytest

from hop3.plugins.oses import arch, base, redhat_family


@pytest.fixture
def ran(monkeypatch) -> list[list[str]]:
    commands: list[list[str]] = []
    monkeypatch.setattr(base.subprocess, "run", lambda cmd, **_kw: commands.append(cmd))
    return commands


def test_services_are_enabled_and_started_under_systemd(monkeypatch, ran) -> None:
    monkeypatch.setattr(base, "has_systemd", lambda: True)
    base.BaseOSStrategy().enable_services("nginx", "crond")
    assert ran == [
        ["systemctl", "enable", "--now", "nginx"],
        ["systemctl", "enable", "--now", "crond"],
    ]


def test_without_systemd_it_refuses_instead_of_pretending(monkeypatch, ran) -> None:
    monkeypatch.setattr(base, "has_systemd", lambda: False)
    with pytest.raises(RuntimeError, match="systemd is not the init system"):
        base.BaseOSStrategy().enable_services("nginx")
    assert ran == []


@pytest.mark.parametrize(
    ("strategy", "cron"),
    [(redhat_family.RedHatFamilyStrategy, "crond"), (arch.ArchStrategy, "cronie")],
)
def test_setup_starts_nginx_and_cron(monkeypatch, ran, strategy, cron) -> None:
    started: list[tuple[str, ...]] = []
    monkeypatch.setattr(strategy, "put_file", lambda *_a, **_k: None)
    monkeypatch.setattr(strategy, "ensure_user", lambda *_a, **_k: None)
    monkeypatch.setattr(strategy, "ensure_packages", lambda *_a, **_k: None)
    monkeypatch.setattr(strategy, "enable_services", lambda _s, *n: started.append(n))
    strategy().setup_server()
    assert started == [("nginx", cron)]
