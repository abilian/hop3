# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Send mail through an :class:`EmailTransport` (EXPERIMENTAL).

The one place Hop3 itself *sends* email — the addon otherwise only stores and
injects credentials for apps. Used by platform notifications (cert-renewal
alerts). Honours the transport's submission mode: implicit TLS on 465, else
STARTTLS on 587.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email import EmailTransport

_TIMEOUT_S = 30


def send_via_transport(
    transport: EmailTransport, recipient: str, subject: str, body: str
) -> None:
    """Send a plain-text message. Raises on any SMTP/connection error.

    The caller decides how to handle failure — :func:`notifications.notify`
    logs-and-swallows (best-effort), the ``notifications test`` command surfaces
    it to the operator.
    """
    msg = EmailMessage()
    msg["From"] = transport.mail_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    if transport.use_implicit_tls:
        with smtplib.SMTP_SSL(
            transport.smtp_host, transport.smtp_port, timeout=_TIMEOUT_S
        ) as server:
            server.login(transport.smtp_user, transport.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(
            transport.smtp_host, transport.smtp_port, timeout=_TIMEOUT_S
        ) as server:
            server.starttls()
            server.login(transport.smtp_user, transport.smtp_password)
            server.send_message(msg)
