from __future__ import annotations

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index() -> str:
    return "Welcome to demo07"
