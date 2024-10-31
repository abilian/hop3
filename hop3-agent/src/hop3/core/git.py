# Copyright (c) 2023-2024, Abilian SAS

"""
Server-side git operations.
"""

import stat
import subprocess
from pathlib import Path
from textwrap import dedent

from attrs import frozen

from hop3.system.constants import GIT_ROOT, HOP3_ROOT, HOP3_SCRIPT

from .app import App


@frozen
class GitManager:
    app: App

    def setup_hook(self):
        setup_hook(self.app)

    def receive_pack(self):
        cmd = ["git-receive-pack", self.app.name]
        subprocess.run(cmd, cwd=GIT_ROOT)

    def upload_pack(self):
        cmd = ["git-upload-pack", self.app.name]
        subprocess.run(cmd, cwd=GIT_ROOT)


def setup_hook(app):
    hook_path = app.repo_path / "hooks" / "post-receive"
    if not hook_path.exists():
        hook_path.parent.mkdir(parents=True)

        # Initialize the repository with a hook to this script
        cmd = ["git", "init", "--quiet", "--bare", app.name]
        subprocess.run(cmd, cwd=GIT_ROOT)

        hook_path.write_text(
            dedent(
                f"""\
                #!/usr/bin/env bash
                set -e; set -o pipefail;
                cat | HOP3_ROOT="{HOP3_ROOT}" {HOP3_SCRIPT} git-hook {app.name}
                """,
            )
        )
        make_executable(hook_path)


def make_executable(path: Path) -> None:
    """Make file executable by the user."""
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
