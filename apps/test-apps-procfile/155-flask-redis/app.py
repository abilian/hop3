"""Flask test app that exercises the Hop3 Redis addon.

Reads the ``REDIS_*`` env vars injected by the addon and does a round-trip:
``SET`` a key, ``GET`` it back, compare.

Exposes two endpoints:

- ``GET /``          — health check; returns "Redis addon OK" if the
                       round-trip succeeds, or the error message.
- ``GET /config``    — echo the connection target and db number (no secrets).

The sibling of ``150-flask-s3``, and it exists for the same reason: the addon's
happy path (addon created → credentials injected → app connects and uses it)
needs one small app that fails loudly when any link in it breaks.

**Why this fixture had to exist.** Nothing in the published catalog declared a
redis addon — only `alpha` entries did — so `--with redis` provisioned a service
no test ever connected to. The gap hid a real bug for as long as it existed: the
installer enabled and restarted Redis with bare `systemctl` under `check=False`,
which on a container did nothing, said nothing, and left Redis down.

Connects by ``REDIS_URL`` when the addon provides one, because that single value
is what carries the password and the db number together — the pieces most likely
to be dropped by a client assembling them by hand.
"""

from __future__ import annotations

import os

import redis
from flask import Flask, jsonify

app = Flask(__name__)

KEY = "hop3-smoke-test"
PAYLOAD = "hello from hop3 flask-redis test app"


def _redis_client() -> redis.Redis:
    """Build a Redis client from env vars injected by the Hop3 addon."""
    url = os.environ.get("REDIS_URL")
    if url:
        return redis.from_url(url, socket_connect_timeout=5)

    # No REDIS_URL: assemble from the parts. Still honours the password, which
    # is the piece a hand-rolled connection most often forgets.
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "127.0.0.1"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=int(os.environ.get("REDIS_DB", "0")),
        password=os.environ.get("REDIS_PASSWORD") or None,
        socket_connect_timeout=5,
    )


@app.route("/")
def index() -> tuple[str, int]:
    """Round-trip a key through the Redis addon."""
    if not (os.environ.get("REDIS_URL") or os.environ.get("REDIS_HOST")):
        return "Redis addon not attached: no REDIS_URL or REDIS_HOST", 500

    try:
        client = _redis_client()
        client.set(KEY, PAYLOAD)
        fetched = client.get(KEY)
    except redis.RedisError as e:
        return f"Redis addon FAILED: {type(e).__name__}: {e}", 500

    if fetched is None:
        return "Redis addon round-trip lost the key: GET returned nothing", 500

    decoded = fetched.decode() if isinstance(fetched, bytes) else str(fetched)
    if decoded != PAYLOAD:
        return (
            f"Redis addon round-trip mismatch: expected {PAYLOAD!r}, got {decoded!r}",
            500,
        )

    return "Redis addon OK", 200


@app.route("/config")
def config() -> tuple[dict, int]:
    """Return the (non-secret) Redis config for debugging."""
    return (
        jsonify(
            {
                "host": os.environ.get("REDIS_HOST", ""),
                "port": os.environ.get("REDIS_PORT", ""),
                "db": os.environ.get("REDIS_DB", ""),
                "has_url": bool(os.environ.get("REDIS_URL")),
                "has_password": bool(os.environ.get("REDIS_PASSWORD")),
            }
        ),
        200,
    )
