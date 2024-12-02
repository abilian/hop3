# Copyright (c) 2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to generate SBOMs."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hop3.config import c
from hop3.util import log

from .base import command

if TYPE_CHECKING:
    from hop3.core.app import App


@command
class BackupCmd:
    """Run a backup for an app."""

    def run(self, app: App) -> None:
        self.run_backup(app)

    def run_backup(self, app: App) -> None:
        # POC implementation, to be replaced later
        path = app.app_path
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
        backup_name = f"{app.name}-{timestamp}.tar.gz"
        backup_dir = c.HOP3_ROOT / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "tar",
            "-zcf",
            str(backup_dir / backup_name),
            str(path),
        ]
        log(f"Running backup for {app.name}...")
        log(f"Command: '{' '.join(cmd)}'", level=1)
        subprocess.run(cmd, check=True)
        log(f"Backup file: {backup_dir / backup_name}")
