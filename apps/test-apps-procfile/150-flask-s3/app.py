"""Flask test app that exercises the Hop3 S3 addon.

Reads `S3_*` env vars injected by the addon and puts the object store
through the operations a real application performs: write, read back,
list, overwrite, and delete.

Exposes:

- ``GET /``          — the full exercise; returns "S3 addon OK" with a
                       summary, or the first failure with its detail.
- ``GET /config``    — the S3 endpoint and bucket, and whether
                       credentials arrived (no secrets).

It uses boto3 because that is what a Python application reaching for S3
uses, so the addon is tested through the same client its users will bring.

**Object keys here are deliberately awkward.** A round-trip on
``hello.txt`` proves very little: every server and every signing
implementation handles it. Spaces, ``+``, ``%``, quotes and non-ASCII are
where signatures and URL encoding come apart, and they did — the Garage
backend double-encoded the key when deleting, so the signature covered
``a%252Bb.txt`` while the request said ``a%2Bb.txt``. Every test in the
suite used a safe key, so nothing caught it until a bucket could not be
emptied and destroying an app left its data behind.
"""

from __future__ import annotations

import os

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify

app = Flask(__name__)

#: Keys chosen to break naive URL encoding and signing, not to look tidy.
#: Each one has cost somebody a day somewhere: a space needs `%20` in the
#: path and `+` must NOT become a space; a literal `+` must survive; `%`
#: must be escaped without being double-escaped; `~` is unreserved and must
#: be left alone; non-ASCII exercises UTF-8 before percent-encoding.
AWKWARD_KEYS = [
    "plain.txt",
    "with space.txt",
    "a+b.txt",
    "100% done.txt",
    "quote'd.txt",
    "tilde~.txt",
    "nested/dir/deeper/файл.txt",
]

PAYLOAD = b"hello from hop3 flask-s3 test app"


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


def _exercise(bucket: str) -> list[str]:
    """
    Run every operation an app performs against its bucket.

    Returns the list of checks that passed. Raises AssertionError on the
    first one that does not, so the endpoint can say which.
    """
    client = _s3_client()
    done = []

    # Write and read back every key, comparing bytes rather than trusting
    # that a 200 means the object arrived intact.
    for key in AWKWARD_KEYS:
        client.put_object(Bucket=bucket, Key=key, Body=PAYLOAD)
        fetched = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if fetched != PAYLOAD:
            msg = f"round-trip mismatch for {key!r}: got {fetched!r}"
            raise AssertionError(msg)
    done.append(f"round-trip x{len(AWKWARD_KEYS)}")

    # Listing must return what was written, including the awkward keys —
    # a backend that mangles a key on write often hides it on list too.
    listed = {
        item["Key"]
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for item in page.get("Contents", [])
    }
    missing = set(AWKWARD_KEYS) - listed
    if missing:
        msg = f"keys written but not listed: {sorted(missing)}"
        raise AssertionError(msg)
    done.append(f"list ({len(listed)} objects)")

    # Overwrite: the second write must win, not append or 412.
    key = AWKWARD_KEYS[0]
    client.put_object(Bucket=bucket, Key=key, Body=b"second")
    if client.get_object(Bucket=bucket, Key=key)["Body"].read() != b"second":
        msg = "overwrite did not replace the object"
        raise AssertionError(msg)
    done.append("overwrite")

    # Delete, and confirm it is really gone rather than trusting the 204.
    for key in AWKWARD_KEYS:
        client.delete_object(Bucket=bucket, Key=key)
    remaining = {
        item["Key"]
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for item in page.get("Contents", [])
    } & set(AWKWARD_KEYS)
    if remaining:
        msg = f"keys survived deletion: {sorted(remaining)}"
        raise AssertionError(msg)
    done.append("delete")

    return done


@app.route("/")
def index() -> tuple[str, int]:
    """Exercise the S3 addon end to end."""
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        return "S3 addon not attached: S3_BUCKET env var missing", 500

    try:
        done = _exercise(bucket)
    except AssertionError as e:
        return f"S3 addon FAILED: {e}", 500
    except (BotoCoreError, ClientError) as e:
        return f"S3 addon FAILED: {type(e).__name__}: {e}", 500

    return f"S3 addon OK: {', '.join(done)}", 200


@app.route("/config")
def config() -> tuple[dict, int]:
    """Return the (non-secret) S3 config for debugging."""
    return (
        jsonify(
            {
                "bucket": os.environ.get("S3_BUCKET", ""),
                "endpoint": os.environ.get("S3_ENDPOINT", ""),
                "region": os.environ.get("S3_REGION", ""),
                # A distinctive token, not a bare field name and not a word
                # like "present". `has_access_key` appeared in the JSON
                # whether the credential arrived or not, so asserting the
                # name proved nothing; and a `contains` on `"key": "value"`
                # would depend on how the serializer spaces its colons
                # (Flask emits compact JSON in production, spaced in debug).
                # A token matches either way.
                "credentials": (
                    "s3-credentials-present"
                    if os.environ.get("S3_ACCESS_KEY")
                    and os.environ.get("S3_SECRET_KEY")
                    else "s3-credentials-missing"
                ),
            }
        ),
        200,
    )
