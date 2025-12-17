# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 34: Native Python app with declarative MySQL provider.

A Flask application demonstrating the [[provider]] section in hop3.toml
for declaring MySQL addon dependencies.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import Flask, jsonify

app = Flask(__name__)

# Get DATABASE_URL from environment (set by Hop3 when addon is attached)
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Get a database connection if DATABASE_URL is configured."""
    if not DATABASE_URL:
        return None
    import mysql.connector

    # Parse DATABASE_URL (mysql://user:pass@host:port/db)
    parsed = urlparse(DATABASE_URL)
    return mysql.connector.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
    )


@app.route("/")
def home():
    """Home page."""
    return jsonify({
        "app": "demo34",
        "type": "native",
        "feature": "declarative-provider",
        "message": "Welcome to demo34 - Declarative MySQL Provider!",
        "database_configured": DATABASE_URL is not None,
    })


@app.route("/db-status")
def db_status():
    """Check database connection status."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured", "message": "DATABASE_URL not set"})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            "status": "connected",
            "version": version,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/db-test")
def db_test():
    """Test database operations (create table, insert, query)."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Create test table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS provider_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Insert a test row
        cursor.execute(
            "INSERT INTO provider_items (name) VALUES (%s)",
            (f"item-{os.urandom(4).hex()}",)
        )
        new_id = cursor.lastrowid
        # Count rows
        cursor.execute("SELECT COUNT(*) FROM provider_items")
        count = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "status": "success",
            "inserted_id": new_id,
            "total_items": count,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
