# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the email loopback-relay on-ramp (ADR 054)."""

from __future__ import annotations

import pytest

from hop3.plugins.email import onramp
from hop3.plugins.email.catcher import CatcherError
from hop3.plugins.email.email import EmailTransport
from hop3.plugins.email.onramp import (
    OnRampError,
    _relay_args,
    configure_catch_backend,
    configure_relay_backend,
)


def _transport() -> EmailTransport:
    return EmailTransport(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="relay-user",
        smtp_password="s3cr3t",
        mail_from="noreply@example.com",
    )


def test_relay_args_maps_transport_to_op():
    assert _relay_args(_transport()) == {
        "relay_host": "smtp.example.com",
        "relay_port": 587,
        "sasl_user": "relay-user",
        "sasl_password": "s3cr3t",
    }


def test_configure_drives_the_rootd_op(fake_rootd):
    assert configure_relay_backend(_transport()) == "fake-rootd"
    assert fake_rootd.calls == [("postfix.configure", _relay_args(_transport()))]


def test_catch_is_refused_when_the_sink_does_not_answer(monkeypatch):
    def silent():
        msg = "nothing answers on 127.0.0.1:1025"
        raise CatcherError(msg)

    monkeypatch.setattr(onramp, "check_sink_answers", silent)

    with pytest.raises(OnRampError, match="nothing answers"):
        configure_catch_backend()
