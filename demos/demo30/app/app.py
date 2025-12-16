# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 30: Native Python Flask application for Hop3 demo."""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)

# Hop3 will set the PORT environment variable
port = int(os.environ.get("PORT", "5000"))


@app.route("/")
def hello_world():
    return "Welcome to demo30"


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "runtime": "native"})


@app.route("/info")
def info():
    """Return environment information."""
    return jsonify({
        "hostname": os.environ.get("HOSTNAME", "unknown"),
        "port": port,
        "flask_env": os.environ.get("FLASK_ENV", "production"),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
