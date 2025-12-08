# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Flask application demonstrating PostgreSQL addon usage."""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)

# DATABASE_URL is injected by Hop3 when a PostgreSQL addon is attached
DATABASE_URL = os.environ.get("DATABASE_URL", "")


@app.route("/")
def index():
    return "Welcome to demo10"


@app.route("/db-status")
def db_status():
    """Check database connectivity."""
    if not DATABASE_URL:
        return jsonify({
            "status": "not_configured",
            "message": "DATABASE_URL not set. Attach a PostgreSQL addon.",
        }), 503

    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            "status": "connected",
            "postgres_version": version,
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
