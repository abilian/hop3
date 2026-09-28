# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""A page behind the access gate, and a public one. Each names who is asking."""

from __future__ import annotations

from flask import Flask, request

app = Flask(__name__)


def _user() -> str:
    # Set by the proxy from the gate's answer; a client's own copy is replaced.
    return request.headers.get("X-Hop3-User", "-")


@app.route("/")
def index() -> str:
    return f"GATED APP: user={_user()}"


@app.route("/public/ping")
def ping() -> str:
    return f"GATED APP PUBLIC: user={_user()}"
