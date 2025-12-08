# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Flask application demonstrating backup/restore with persistent data."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

# Data file stored in the app's data directory (will be backed up)
# Hop3 backs up <app_path>/data, so we use ../data relative to src/
# This defaults to /var/hop3/apps/<app_name>/data in production
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_FILE = DATA_DIR / "notes.json"


def ensure_data_dir():
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_notes() -> list:
    """Read notes from data file."""
    ensure_data_dir()
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_notes(notes: list) -> None:
    """Save notes to data file."""
    ensure_data_dir()
    DATA_FILE.write_text(json.dumps(notes, indent=2))


@app.route("/")
def index():
    return "Welcome to demo12"


@app.route("/notes", methods=["GET"])
def list_notes():
    """List all notes."""
    return jsonify({
        "notes": get_notes(),
        "count": len(get_notes()),
    })


@app.route("/notes", methods=["POST"])
def add_note():
    """Add a new note."""
    import time
    data = request.get_json() or {}
    content = data.get("content", request.args.get("content", ""))

    if not content:
        return jsonify({"error": "content required"}), 400

    notes = get_notes()
    note = {
        "id": len(notes) + 1,
        "content": content,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    notes.append(note)
    save_notes(notes)

    return jsonify({"status": "created", "note": note}), 201


@app.route("/notes/add/<content>")
def add_note_simple(content: str):
    """Add a note via GET (for easy demo testing)."""
    import time
    notes = get_notes()
    note = {
        "id": len(notes) + 1,
        "content": content,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    notes.append(note)
    save_notes(notes)

    return jsonify({"status": "created", "note": note})


@app.route("/notes/clear")
def clear_notes():
    """Clear all notes (for demo purposes)."""
    save_notes([])
    return jsonify({"status": "cleared"})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
