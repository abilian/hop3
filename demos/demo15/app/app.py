# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 15: Docker app with PostgreSQL addon.

A Flask application running in Docker that connects to a PostgreSQL database
provisioned via Hop3 addons.
"""

import os

from flask import Flask, jsonify

app = Flask(__name__)

# Get DATABASE_URL from environment (set by Hop3 when addon is attached)
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Get a database connection if DATABASE_URL is configured."""
    if not DATABASE_URL:
        return None
    import psycopg2

    return psycopg2.connect(DATABASE_URL)


@app.route("/")
def home():
    """Home page."""
    return jsonify({
        "app": "demo15",
        "type": "docker",
        "message": "Welcome to demo15 - Docker + PostgreSQL!",
        "database_configured": DATABASE_URL is not None,
    })


@app.route("/db-status")
def db_status():
    """Check database connection status."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured", "message": "DATABASE_URL not set"})

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
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
        with conn.cursor() as cur:
            # Create test table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS demo_items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Insert a test row
            cur.execute(
                "INSERT INTO demo_items (name) VALUES (%s) RETURNING id",
                (f"item-{os.urandom(4).hex()}",)
            )
            new_id = cur.fetchone()[0]
            # Count rows
            cur.execute("SELECT COUNT(*) FROM demo_items")
            count = cur.fetchone()[0]
        conn.commit()
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
