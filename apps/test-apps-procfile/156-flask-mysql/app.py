"""Flask test app that exercises the Hop3 MySQL addon.

Reads the ``MYSQL_*`` env vars injected by the addon, writes a row and reads it
back. ``GET /`` returns "MySQL addon OK" when the round-trip succeeds, or the
error.

The sibling of ``155-flask-redis``: one small app that fails loudly when any
link between the addon and the app breaks.
"""

from __future__ import annotations

import os

import pymysql
from flask import Flask

app = Flask(__name__)

PAYLOAD = "hello from hop3 flask-mysql test app"


@app.route("/")
def index() -> tuple[str, int]:
    """Round-trip a row through the MySQL addon."""
    if not os.environ.get("MYSQL_HOST"):
        return "MySQL addon not attached: no MYSQL_HOST", 500

    try:
        conn = pymysql.connect(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ["MYSQL_PORT"]),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"],
            connect_timeout=5,
            autocommit=True,
        )
        with conn, conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS smoke (v text)")
            cur.execute("DELETE FROM smoke")
            cur.execute("INSERT INTO smoke VALUES (%s)", (PAYLOAD,))
            cur.execute("SELECT v FROM smoke")
            row = cur.fetchone()
    except pymysql.MySQLError as e:
        return f"MySQL addon FAILED: {type(e).__name__}: {e}", 500

    if row is None or row[0] != PAYLOAD:
        return f"MySQL addon round-trip mismatch: got {row!r}", 500
    return "MySQL addon OK", 200
