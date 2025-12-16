# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 29: Native Python app with MySQL addon - Page Counter.

A simple Flask application deployed natively (without Docker) that connects
to a MySQL database provisioned via Hop3 addons. Implements a basic page view counter.
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import Flask, jsonify

app = Flask(__name__)

# Get DATABASE_URL from environment (set by Hop3 when addon is attached)
# MySQL addon provides: DATABASE_URL, MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Get a database connection if DATABASE_URL is configured."""
    if not DATABASE_URL:
        return None

    import mysql.connector

    # Use individual env vars for more reliability
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER"),
        password=os.environ.get("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE"),
    )


def init_db():
    """Initialize the database table if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS page_views (
                id INT AUTO_INCREMENT PRIMARY KEY,
                page VARCHAR(100) NOT NULL,
                view_count INT DEFAULT 0,
                last_viewed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_page (page)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        return False


def increment_counter(page: str = "home") -> int:
    """Increment the page view counter and return the new count."""
    conn = get_db_connection()
    if not conn:
        return -1

    try:
        cursor = conn.cursor()
        # Insert or update the counter
        cursor.execute("""
            INSERT INTO page_views (page, view_count)
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE view_count = view_count + 1
        """, (page,))
        conn.commit()

        # Get the current count
        cursor.execute("SELECT view_count FROM page_views WHERE page = %s", (page,))
        result = cursor.fetchone()
        count = result[0] if result else 0

        cursor.close()
        conn.close()
        return count
    except Exception:
        return -1


@app.route("/")
def home():
    """Home page with page counter."""
    db_configured = DATABASE_URL is not None

    if db_configured:
        count = increment_counter("home")
        if count == -1:
            return jsonify({
                "app": "demo29",
                "type": "native + mysql",
                "message": "Welcome to demo29 - Native MySQL Page Counter!",
                "database_configured": True,
                "error": "Failed to increment counter",
            })
        return jsonify({
            "app": "demo29",
            "type": "native + mysql",
            "message": "Welcome to demo29 - Native MySQL Page Counter!",
            "database_configured": True,
            "page_views": count,
            "timestamp": datetime.now().isoformat(),
        })

    return jsonify({
        "app": "demo29",
        "type": "native + mysql",
        "message": "Welcome to demo29 - Native MySQL Page Counter!",
        "database_configured": False,
        "hint": "Attach a MySQL addon to enable the counter",
    })


@app.route("/db-status")
def db_status():
    """Check database connection status."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured", "message": "DATABASE_URL not set"})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            "status": "connected",
            "version": version,
            "database": os.environ.get("MYSQL_DATABASE"),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/db-init")
def db_init():
    """Initialize the database table."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured"}), 400

    success = init_db()
    if success:
        return jsonify({"status": "success", "message": "Database initialized"})
    return jsonify({"status": "error", "message": "Failed to initialize"}), 500


@app.route("/counter")
def counter():
    """Get the current page view count without incrementing."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT page, view_count, last_viewed FROM page_views ORDER BY view_count DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        counters = [
            {"page": row[0], "views": row[1], "last_viewed": row[2].isoformat() if row[2] else None}
            for row in rows
        ]
        return jsonify({"status": "success", "counters": counters})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/db-test")
def db_test():
    """Test database operations (create table, insert, query)."""
    if not DATABASE_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        # Initialize DB first
        init_db()

        # Increment counter
        count = increment_counter("test")

        return jsonify({
            "status": "success",
            "test_page_views": count,
            "message": "MySQL operations working!",
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
