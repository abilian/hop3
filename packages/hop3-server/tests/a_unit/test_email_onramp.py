# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the email loopback-relay on-ramp (ADR 054)."""

from __future__ import annotations

from hop3.plugins.email.email import EmailTransport
from hop3.plugins.email.onramp import _relay_args, configure_relay_backend


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


def test_configure_skipped_under_pytest():
    # No live rootd in unit tests: the guard returns None and never raises.
    assert configure_relay_backend(_transport()) is None
