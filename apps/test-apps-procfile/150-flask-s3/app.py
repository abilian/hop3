"""Flask test app that exercises the Hop3 S3 addon.

Reads `S3_*` env vars injected by the addon and does a round-trip:
``PUT`` a test object, ``GET`` it back, compare.

Exposes two endpoints:

- ``GET /``          — health check; returns "S3 addon OK" if the
                       round-trip succeeds, or the error message.
- ``GET /config``    — echo the S3 endpoint and bucket (no secrets).

This is a deliberately minimal smoke test — it uses boto3 because
that's what most Python apps using S3 use. The test app demonstrates
the happy path for the plugin: addon creation → credentials injected
→ app reads them and uses them.
"""

from __future__ import annotations

import os

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify

app = Flask(__name__)


def _s3_client():
    """Build an S3 client from env vars injected by the Hop3 addon."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT") or os.environ["AWS_ENDPOINT_URL"],
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY")
        or os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY")
        or os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@app.route("/")
def index() -> tuple[str, int]:
    """Round-trip a test object through the S3 addon."""
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        return "S3 addon not attached: S3_BUCKET env var missing", 500

    key = "hop3-smoke-test.txt"
    payload = b"hello from hop3 flask-s3 test app"

    try:
        client = _s3_client()
        client.put_object(Bucket=bucket, Key=key, Body=payload)
        response = client.get_object(Bucket=bucket, Key=key)
        fetched = response["Body"].read()
    except (BotoCoreError, ClientError) as e:
        return f"S3 addon FAILED: {type(e).__name__}: {e}", 500

    if fetched != payload:
        return (
            f"S3 addon round-trip mismatch: expected {payload!r}, got {fetched!r}",
            500,
        )

    return "S3 addon OK", 200


@app.route("/config")
def config() -> tuple[dict, int]:
    """Return the (non-secret) S3 config for debugging."""
    return (
        jsonify(
            {
                "bucket": os.environ.get("S3_BUCKET", ""),
                "endpoint": os.environ.get("S3_ENDPOINT", ""),
                "region": os.environ.get("S3_REGION", ""),
                "has_access_key": bool(os.environ.get("S3_ACCESS_KEY")),
                "has_secret_key": bool(os.environ.get("S3_SECRET_KEY")),
            }
        ),
        200,
    )
