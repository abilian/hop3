#!/usr/bin/env python
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Background worker that processes tasks from a queue.

This is a simple demonstration worker. In production, you would use
a proper task queue like Celery, RQ, or Dramatiq with Redis/RabbitMQ.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Shared file for demo purposes
TASK_FILE = Path("/tmp/demo11_tasks.json")
WORKER_LOG = Path("/tmp/demo11_worker.log")


def log(message: str) -> None:
    """Log a message to both stdout and log file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with open(WORKER_LOG, "a") as f:
        f.write(line + "\n")


def get_tasks() -> list:
    """Read tasks from shared file."""
    if TASK_FILE.exists():
        return json.loads(TASK_FILE.read_text())
    return []


def save_tasks(tasks: list) -> None:
    """Save tasks to shared file."""
    TASK_FILE.write_text(json.dumps(tasks))


def process_task(task: dict) -> None:
    """Process a single task."""
    log(f"Processing task {task['id']}: {task['message']}")
    # Simulate work
    time.sleep(2)
    task["status"] = "completed"
    task["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log(f"Completed task {task['id']}")


def main() -> None:
    """Main worker loop."""
    log("Worker started. Waiting for tasks...")

    while True:
        try:
            tasks = get_tasks()
            pending = [t for t in tasks if t.get("status") == "pending"]

            if pending:
                task = pending[0]
                process_task(task)
                save_tasks(tasks)
            else:
                # No tasks, wait a bit
                time.sleep(1)

        except KeyboardInterrupt:
            log("Worker shutting down...")
            sys.exit(0)
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
