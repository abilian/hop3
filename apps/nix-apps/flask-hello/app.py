# SPDX-License-Identifier: Apache-2.0
# Simple Flask hello world app for Nix integration testing

from flask import Flask

app = Flask(__name__)


@app.route("/")
def hello():
    return "Hello from Nix-built Flask!"


@app.route("/health")
def health():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
