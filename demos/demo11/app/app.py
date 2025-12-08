# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Flask application demonstrating background workers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

# Shared file for demo purposes (in production, use Redis/database)
TASK_FILE = Path("/tmp/demo11_tasks.json")


def get_tasks() -> list:
    """Read tasks from shared file."""
    if TASK_FILE.exists():
        return json.loads(TASK_FILE.read_text())
    return []


def add_task(task: dict) -> None:
    """Add a task to the queue."""
    tasks = get_tasks()
    tasks.append(task)
    TASK_FILE.write_text(json.dumps(tasks))


@app.route("/")
def index():
    return "Welcome to demo11"


@app.route("/enqueue/<message>")
def enqueue(message: str):
    """Enqueue a task for the background worker."""
    import time
    task = {
        "id": int(time.time() * 1000),
        "message": message,
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    add_task(task)
    return jsonify({
        "status": "queued",
        "task": task,
    })


@app.route("/tasks")
def list_tasks():
    """List all tasks and their status."""
    return jsonify({
        "tasks": get_tasks(),
        "count": len(get_tasks()),
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "process": "web"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
