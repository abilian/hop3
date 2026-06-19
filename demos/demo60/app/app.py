# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tiny Flask app for demo60 (the CLI-surface tour).

Just enough surface to make app-scoped CLI commands meaningful:
  /         identifies the app (content-checkable by the demo)
  /health   liveness for [healthcheck]
  /env      lists the (non-secret) env var names Hop3 injected
  /db       reports whether a DATABASE_URL was wired in (e.g. by `addon attach`)
"""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index() -> str:
    return "Welcome to demo60 — the Hop3 CLI surface tour."


@app.route("/health")
def health():
    return jsonify(status="healthy")


@app.route("/env")
def env():
    # Names only — never echo values (some are secrets).
    return jsonify(keys=sorted(os.environ.keys()))


@app.route("/db")
def db():
    url = os.environ.get("DATABASE_URL", "")
    return jsonify(
        database_url_set=bool(url), scheme=url.split("://", 1)[0] if url else None
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
