# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Email addon round-trip: send through the injected relay, read back from Mailpit.

The app sends exactly as a stock Flask or Django app does, from the variables
the addon injects (SMTP_HOST, SMTP_PORT, SMTP_FROM). The catch backend relays
to Mailpit on the same box, whose API this fixture reads to prove delivery.
"""

from __future__ import annotations

import json
import os
import smtplib
import time
import uuid
from email.message import EmailMessage
from http.client import HTTPConnection

from flask import Flask

app = Flask(__name__)

#: The catch backend's sink (hop3 plugins/email/catcher.py).
MAILPIT = ("127.0.0.1", 8025)


@app.route("/")
def index():
    if not os.environ.get("SMTP_HOST"):
        return "No SMTP_HOST injected: the email addon is not wired", 500
    return f"Email addon wired: {os.environ['SMTP_HOST']}:{os.environ['SMTP_PORT']}"


@app.route("/mail-roundtrip")
def mail_roundtrip():
    token = uuid.uuid4().hex
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = "probe@hop3.test"
    message["Subject"] = f"hop3 email round-trip {token}"
    message.set_content("Sent by the flask-email fixture.")
    with smtplib.SMTP(
        os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), timeout=15
    ) as smtp:
        smtp.send_message(message)

    # Postfix delivers asynchronously.
    for _ in range(30):
        if token in _captured_subjects():
            return f"captured {token}"
        time.sleep(1)
    return f"sent {token}, but the catch sink never received it", 500


def _captured_subjects() -> str:
    connection = HTTPConnection(*MAILPIT, timeout=5)
    try:
        connection.request("GET", "/api/v1/messages?limit=50")
        payload = json.loads(connection.getresponse().read())
    finally:
        connection.close()
    return " ".join(m.get("Subject", "") for m in payload.get("messages") or [])
