# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A small Flask application for the Hop3 demo (demo 22)."""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)

# Hop3 sets PORT to tell the app which port to bind; GREETING shows how an
# environment variable flows into the app's configuration.
PORT = int(os.environ.get("PORT", "5000"))
GREETING = os.environ.get("GREETING", "Hello from demo22")


@app.route("/")
def index() -> str:
    return f"<h1>{GREETING} — a Flask app on Hop3</h1>"


@app.route("/api/info")
def info():
    return jsonify(app="demo22", framework="flask", greeting=GREETING)


@app.route("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
