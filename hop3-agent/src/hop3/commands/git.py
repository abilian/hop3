# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Internal CLI commands to manage git hooks."""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

from click import argument

from hop3.core.app import App, get_app
from hop3.deploy import do_deploy
from hop3.system.constants import APP_ROOT, GIT_ROOT, HOP3_ROOT, HOP3_SCRIPT
from hop3.util import sanitize_app_name
from hop3.util.console import echo

from .cli import hop3
from .util import make_executable


@hop3.command("git-hook")
@argument("app_name")
def cmd_git_hook(app_name: str) -> None:
    """INTERNAL: Post-receive git hook."""
    app = App(app_name)

    for line in sys.stdin:
        _oldrev, newrev, _refname = line.strip().split(" ")

        # Handle pushes
        if not app.app_path.exists():
            echo(f"-----> Creating app '{app_name}'", fg="green")
            app.create()

            cmd = ["git", "clone", "--quiet", app.repo_path, app_name]
            subprocess.run(cmd, cwd=APP_ROOT)

        do_deploy(app_name, newrev=newrev)


@hop3.command("git-receive-pack")
@argument("app_name")
def cmd_git_receive_pack(app_name: str) -> None:
    """INTERNAL: Handle git pushes for an app."""
    app_name = sanitize_app_name(app_name)
    app = get_app(app_name, check=False)
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

    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    cmd = ["git-receive-pack", app.name]
    subprocess.run(cmd, cwd=GIT_ROOT)


@hop3.command("git-upload-pack")
@argument("app_name")
def cmd_git_upload_pack(app_name: str) -> None:
    """INTERNAL: Handle git upload pack for an app."""
    app = get_app(app_name)

    # Handle the actual receive. Will be called with 'git-hook' after it happens
    cmd = ["git-upload-pack", app.name]
    subprocess.run(cmd, cwd=GIT_ROOT)
