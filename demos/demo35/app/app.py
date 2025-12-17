# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 35: Native Python app with declarative Redis provider.

A Flask application demonstrating the [[provider]] section in hop3.toml
for declaring Redis addon dependencies.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)

# Get REDIS_URL from environment (set by Hop3 when addon is attached)
REDIS_URL = os.environ.get("REDIS_URL")


def get_redis_client():
    """Get a Redis client if REDIS_URL is configured."""
    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL)


@app.route("/")
def home():
    """Home page."""
    return jsonify({
        "app": "demo35",
        "type": "native",
        "feature": "declarative-provider",
        "message": "Welcome to demo35 - Declarative Redis Provider!",
        "redis_configured": REDIS_URL is not None,
    })


@app.route("/redis-status")
def redis_status():
    """Check Redis connection status."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured", "message": "REDIS_URL not set"})

    try:
        client = get_redis_client()
        info = client.info()
        return jsonify({
            "status": "connected",
            "version": info.get("redis_version"),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/counter")
def counter():
    """Get current counter value."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        value = client.get("demo35:counter")
        return jsonify({
            "counter": int(value) if value else 0,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/counter/increment")
def counter_increment():
    """Increment counter."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        new_value = client.incr("demo35:counter")
        return jsonify({
            "action": "increment",
            "counter": new_value,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/cache/set/<key>/<value>")
def cache_set(key: str, value: str):
    """Set a cache value."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        client.set(f"demo35:{key}", value, ex=3600)  # 1 hour expiry
        return jsonify({
            "action": "set",
            "key": key,
            "value": value,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/cache/get/<key>")
def cache_get(key: str):
    """Get a cache value."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        value = client.get(f"demo35:{key}")
        if value:
            value = value.decode("utf-8")
        return jsonify({
            "action": "get",
            "key": key,
            "value": value,
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
