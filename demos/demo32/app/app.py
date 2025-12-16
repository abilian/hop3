# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 32: Native Python app with Redis addon.

A Flask application deployed natively that connects to Redis
provisioned via Hop3 addons.
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
        "app": "demo32",
        "type": "native",
        "message": "Welcome to demo32 - Native Python + Redis!",
        "redis_configured": REDIS_URL is not None,
    })


@app.route("/redis-status")
def redis_status():
    """Check Redis connection status."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured", "message": "REDIS_URL not set"})

    try:
        client = get_redis_client()
        info = client.info("server")
        return jsonify({
            "status": "connected",
            "redis_version": info.get("redis_version"),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/counter")
def get_counter():
    """Get current counter value."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        value = client.get("demo32:counter")
        return jsonify({
            "counter": int(value) if value else 0,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/counter/increment")
def increment_counter():
    """Increment and return the counter."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        new_value = client.incr("demo32:counter")
        return jsonify({
            "counter": new_value,
            "action": "incremented",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/counter/reset")
def reset_counter():
    """Reset the counter to zero."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        client.set("demo32:counter", 0)
        return jsonify({
            "counter": 0,
            "action": "reset",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/cache/set/<key>/<value>")
def cache_set(key, value):
    """Set a cache value with 60s TTL."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        client.setex(f"demo32:cache:{key}", 60, value)
        return jsonify({
            "key": key,
            "value": value,
            "ttl": 60,
            "action": "set",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/cache/get/<key>")
def cache_get(key):
    """Get a cached value."""
    if not REDIS_URL:
        return jsonify({"status": "not_configured"}), 400

    try:
        client = get_redis_client()
        value = client.get(f"demo32:cache:{key}")
        ttl = client.ttl(f"demo32:cache:{key}")
        return jsonify({
            "key": key,
            "value": value.decode() if value else None,
            "ttl": ttl if ttl > 0 else None,
            "found": value is not None,
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
