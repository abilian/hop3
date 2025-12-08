# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 17: Docker multi-container application.

A Flask application that runs alongside a Redis container,
both defined in a custom docker-compose.yml file.
"""

import os

import redis
from flask import Flask, jsonify

app = Flask(__name__)

# Redis is available at 'redis' hostname (docker-compose networking)
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))


def get_redis_client():
    """Get Redis client (always available via docker-compose)."""
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@app.route("/")
def home():
    """Home page."""
    return jsonify({
        "app": "demo17",
        "type": "docker-compose-multi",
        "message": "Welcome to demo17 - Multi-container Docker app!",
        "services": ["web", "redis"],
    })


@app.route("/redis-status")
def redis_status():
    """Check Redis connection status."""
    try:
        client = get_redis_client()
        info = client.info("server")
        return jsonify({
            "status": "connected",
            "redis_version": info.get("redis_version"),
            "redis_host": REDIS_HOST,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/visits")
def get_visits():
    """Get visit count (demonstrates shared state)."""
    try:
        client = get_redis_client()
        visits = client.incr("demo17:visits")
        return jsonify({
            "visits": visits,
            "message": f"This page has been visited {visits} times!",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/visits/reset")
def reset_visits():
    """Reset visit counter (for demo testing)."""
    try:
        client = get_redis_client()
        client.delete("demo17:visits")
        return jsonify({"status": "reset", "visits": 0})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/data/<key>")
def get_data(key):
    """Get a value from Redis."""
    try:
        client = get_redis_client()
        value = client.get(f"demo17:data:{key}")
        return jsonify({
            "key": key,
            "value": value,
            "found": value is not None,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/data/<key>/<value>")
def set_data(key, value):
    """Set a value in Redis."""
    try:
        client = get_redis_client()
        client.set(f"demo17:data:{key}", value)
        return jsonify({
            "key": key,
            "value": value,
            "action": "set",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint."""
    try:
        client = get_redis_client()
        client.ping()
        return jsonify({"status": "healthy", "redis": "connected"})
    except Exception:
        return jsonify({"status": "degraded", "redis": "disconnected"}), 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
