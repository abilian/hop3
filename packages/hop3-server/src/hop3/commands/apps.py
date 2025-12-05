# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register
from hop3.orm import AppRepository
from hop3.project.procfile import parse_procfile

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


def _get_instance_count(app: App) -> int | str:
    """Get the number of running instances for an app.

    For uWSGI apps: Returns worker count from SCALING file
    For Docker apps: Returns running container count

    Returns:
        Instance count, or "-" if not applicable/unknown
    """
    if app.runtime == "docker-compose":
        return _get_docker_container_count(app)
    return _get_uwsgi_worker_count(app)


def _get_uwsgi_worker_count(app: App) -> int:
    """Get worker count from SCALING file for uWSGI apps."""
    scaling_file = app.virtualenv_path / "SCALING"
    if scaling_file.exists():
        try:
            worker_map = parse_procfile(scaling_file)
            return sum(int(v) for v in worker_map.values())
        except (OSError, ValueError):
            return -1  # Error state
    return 0


def _get_docker_container_count(app: App) -> int | str:
    """Get running container count for Docker apps."""
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                app.name,
                "ps",
                "--format",
                "{{.State}}",
            ],
            cwd=app.src_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return "-"

        # Count running containers
        states = result.stdout.strip().split("\n")
        running = sum(1 for s in states if s and "running" in s.lower())
        return running

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return "-"


@register
@dataclass(frozen=True)
class AppsCmd(Command):
    """List all applications."""

    db_session: Session
    name: ClassVar[str] = "apps"

    def call(self, *args):
        app_repo = AppRepository(session=self.db_session)
        apps = app_repo.list()
        if not apps:
            return [{"t": "text", "text": "There are no applications deployed."}]

        rows = []
        for app in apps:
            instance_count = _get_instance_count(app)
            rows.append([app.name, app.run_state.name, instance_count])

        return [
            {
                "t": "table",
                "headers": ["Name", "Status", "Instances"],
                "rows": rows,
            }
        ]
