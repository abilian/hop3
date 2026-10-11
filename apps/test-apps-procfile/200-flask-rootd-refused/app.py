"""
Asks hop3-rootd for its handshake from inside an app, and reports what came back.

Every native app runs as hop3, the uid rootd admits, so an app's code could
call every privileged op. rootd now refuses a caller inside the app runtime:
it closes the connection without answering.
"""

import json
import socket

from flask import Flask

app = Flask(__name__)

ROOTD_SOCKET = "/run/hop3-rootd/socket"
HANDSHAKE = {"v": 1, "id": "app-probe", "op": "daemon.handshake", "args": {}}


@app.route("/")
def index():
    return f"rootd from an app: {_ask_rootd()}"


def _ask_rootd() -> str:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(ROOTD_SOCKET)
            conn.sendall(json.dumps(HANDSHAKE).encode() + b"\n")
            reply = conn.recv(4096)
    except OSError as e:
        return f"refused ({e.__class__.__name__})"
    return "answered" if reply else "refused (closed without a reply)"
