# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register
from hop3.orm import AppRepository
from hop3.project.procfile import parse_procfile

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
            worker_count = 0
            scaling_file = app.virtualenv_path / "SCALING"
            if scaling_file.exists():
                try:
                    worker_map = parse_procfile(scaling_file)
                    worker_count = sum(int(v) for v in worker_map.values())
                except (OSError, ValueError):
                    # In case of malformed file or race condition
                    worker_count = -1  # Indicates an error state

            rows.append([app.name, app.run_state.name, worker_count])

        return [
            {
                "t": "table",
                "headers": ["Name", "Status", "Workers"],
                "rows": rows,
            }
        ]
