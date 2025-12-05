# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Sample Flask application for Hop3 demo."""

from __future__ import annotations

import os

from flask import Flask

app = Flask(__name__)

# Hop3 will set the PORT environment variable to tell our app what port to listen on.
port = int(os.environ.get("PORT", "5000"))


@app.route("/")
def hello_world():
    return "<h1>Hello, Hop3!</h1><p>Your Flask application is running.</p>"


@app.route("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
