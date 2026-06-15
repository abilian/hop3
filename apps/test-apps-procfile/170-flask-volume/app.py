"""Flask test app proving Hop3 persistent volumes (ADR 046 §2).

`hop3.toml` declares:

    [[volumes]]
    name = "store"
    target = "data/store"

Hop3 links ``data/store`` (in the app's source tree) to a directory under the
app's data root (`<app>/volumes/store/`), which lives outside `src/` and so
survives the redeploy that wipes `src/`. The app proves the link was realized:
``data/store`` must resolve to a path under `.../volumes/store`, and it must be
writable. It serves "VOLUME OK" only when both hold.

(Survival *across* redeploys is covered by the unit tests; this app proves the
volume is correctly mounted and writable through a real deploy.)
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

app = Flask(__name__)

TARGET = "data/store"


@app.route("/")
def index() -> tuple[str, int]:
    """Pass only if the target is a writable, persistent volume."""
    target = Path(TARGET)
    problems = []

    realpath = os.path.realpath(target)
    if "/volumes/store" not in realpath:
        problems.append(f"not backed by a persistent volume: realpath={realpath!r}")

    try:
        target.mkdir(parents=True, exist_ok=True)
        marker = target / "marker.txt"
        marker.write_text("persisted")
        if marker.read_text() != "persisted":
            problems.append("write/read mismatch")
    except OSError as e:
        problems.append(f"volume not writable: {type(e).__name__}: {e}")

    if problems:
        return "VOLUME FAILED: " + "; ".join(problems), 500
    return "VOLUME OK", 200


@app.route("/config")
def config() -> tuple[str, int]:
    """Echo where the volume target actually resolves to."""
    return f"target={TARGET}\nrealpath={os.path.realpath(TARGET)}\n", 200
