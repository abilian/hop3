# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared SSL-verify resolution for RPC + streaming (audit 2026-06 B1).

The streaming deploy path used to hand-roll ``config.get("verify_ssl", True)``,
ignoring a pinned ``ssl_cert`` (stream fails while /rpc succeeds -> failure
reported on a running deploy) and passing a *string* ``"false"`` to requests
(read as a CA path -> opaque OSError). Both now route through
``resolve_ssl_verification``.
"""

from __future__ import annotations

from hop3_cli.config import Config
from hop3_cli.rpc.client import resolve_ssl_verification


def test_http_url_needs_no_verification():
    assert resolve_ssl_verification("http://localhost:8000", Config(data={})) is False


def test_https_defaults_to_system_ca():
    assert resolve_ssl_verification("https://host", Config(data={})) is True


def test_pinned_cert_is_returned_for_streaming():
    cfg = Config(data={"ssl_cert": "/etc/hop3/cert.pem"})
    assert resolve_ssl_verification("https://host", cfg) == "/etc/hop3/cert.pem"


def test_string_false_disables_verification_not_treated_as_path():
    # The bug: a string "false" used to reach requests as verify="false" (a CA
    # path). It must parse to the bool False instead.
    cfg = Config(data={"verify_ssl": "false"})
    assert resolve_ssl_verification("https://host", cfg) is False


def test_bool_false_disables_verification():
    cfg = Config(data={"verify_ssl": False})
    assert resolve_ssl_verification("https://host", cfg) is False


def test_pinned_cert_wins_over_disabled_flag():
    cfg = Config(data={"ssl_cert": "/c.pem", "verify_ssl": "false"})
    assert resolve_ssl_verification("https://host", cfg) == "/c.pem"
