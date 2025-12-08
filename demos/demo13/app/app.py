# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Flask application demonstrating build hooks."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

# These files are created by build hooks
BUILD_INFO_FILE = Path(__file__).parent / "build_info.txt"
ASSETS_DIR = Path(__file__).parent / "static"


@app.route("/")
def index():
    return "Welcome to demo13"


@app.route("/build-info")
def build_info():
    """Show build information created by hooks."""
    info = {
        "build_info_exists": BUILD_INFO_FILE.exists(),
        "assets_compiled": (ASSETS_DIR / "app.min.css").exists(),
    }

    if BUILD_INFO_FILE.exists():
        info["build_info"] = BUILD_INFO_FILE.read_text().strip()

    if (ASSETS_DIR / "app.min.css").exists():
        info["css_content"] = (ASSETS_DIR / "app.min.css").read_text().strip()

    return jsonify(info)


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
