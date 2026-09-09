# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Only the server knows its own public address.

A client holds an SSH target, which says nothing about whether nginx and TLS
front the API. `admin:server-url` is how it finds out, so everyday traffic can
go over HTTPS instead of tunnelling through a root shell.
"""

from __future__ import annotations

import pytest

from hop3.config import config
from hop3.server.cli.admin import AdminServerUrl


@pytest.fixture
def admin_domain(monkeypatch):
    """Set (or clear) the server's configured public domain."""

    def configure(domain: str):
        monkeypatch.setattr(type(config), "ADMIN_DOMAIN", property(lambda _s: domain))

    return configure


def test_prints_the_https_base_url(admin_domain, capsys):
    admin_domain("hop3.example.com")
    AdminServerUrl().run()
    assert capsys.readouterr().out.strip() == "https://hop3.example.com"


def test_prints_nothing_without_an_admin_domain(admin_domain, capsys):
    """
    The empty answer is the answer, not a failure.

    There is no HTTPS endpoint, so the caller keeps its SSH tunnel. Exiting
    non-zero is reserved for a server too old to have this command at all, which
    the client reports differently.
    """
    admin_domain("")
    AdminServerUrl().run()
    assert capsys.readouterr().out.strip() == ""


def test_is_registered_under_the_admin_namespace():
    assert AdminServerUrl.name == "admin:server-url"
