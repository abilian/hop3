# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 14 Flask application with Redis support.

This application demonstrates Redis addon integration with Hop3.
It reads REDIS_URL from environment variables to connect to Redis.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)


def get_redis_connection():
    """Get Redis connection from REDIS_URL environment variable."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis

        return redis.from_url(redis_url, decode_responses=True)
    except Exception:
        return None


@app.route("/")
def index():
    """Welcome page."""
    return jsonify(
        {
            "message": "Welcome to demo14 - Redis Addon Demo",
            "endpoints": {
                "/": "This welcome message",
                "/redis-status": "Check Redis connection status",
                "/counter": "Get current counter value",
                "/counter/increment": "Increment the counter",
                "/counter/reset": "Reset the counter to 0",
            },
        }
    )


@app.route("/redis-status")
def redis_status():
    """Check Redis connection status."""
    redis_url = os.environ.get("REDIS_URL")

    if not redis_url:
        return jsonify(
            {
                "status": "not_configured",
                "message": "REDIS_URL not set. Attach a Redis addon.",
            }
        )

    try:
        import redis

        r = redis.from_url(redis_url, decode_responses=True)
        pong = r.ping()

        if pong:
            # Get some server info
            info = r.info("server")
            return jsonify(
                {
                    "status": "connected",
                    "redis_version": info.get("redis_version", "unknown"),
                    "database": redis_url.split("/")[-1] if "/" in redis_url else "0",
                }
            )
        return jsonify({"status": "error", "message": "Redis did not respond to PING"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/counter")
def get_counter():
    """Get the current counter value."""
    r = get_redis_connection()
    if not r:
        return jsonify({"error": "Redis not configured"}), 500

    try:
        value = r.get("demo14:counter")
        return jsonify({"counter": int(value) if value else 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/counter/increment")
def increment_counter():
    """Increment the counter and return new value."""
    r = get_redis_connection()
    if not r:
        return jsonify({"error": "Redis not configured"}), 500

    try:
        new_value = r.incr("demo14:counter")
        return jsonify({"counter": new_value, "action": "incremented"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/counter/reset")
def reset_counter():
    """Reset the counter to 0."""
    r = get_redis_connection()
    if not r:
        return jsonify({"error": "Redis not configured"}), 500

    try:
        r.set("demo14:counter", 0)
        return jsonify({"counter": 0, "action": "reset"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
