# Flask app with uWSGI for Hop3 Nix integration
from __future__ import annotations

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index() -> str:
    return "Hello World, from Flask/uWSGI via Nix!"
