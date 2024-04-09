# Copyright (c) 2023-2024, Abilian SAS
# Copyright (c) 2016 Rui Carmo

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from click import argument
from click import secho as echo

from hop3.core.app import App, get_app
from hop3.deploy import do_deploy
from hop3.system.constants import APP_ROOT, GIT_ROOT, HOP3_ROOT, HOP3_SCRIPT
from hop3.util import sanitize_app_name

from .cli import hop3


@hop3.command("git-hook")
@argument("app")
def cmd_git_hook(app: str) -> None:
    """INTERNAL: Post-receive git hook"""

    app_obj = App(app)
    app_path = Path(app_obj.app_path)
    data_path = Path(app_obj.data_path)

    for line in sys.stdin:
        # pylint: disable=unused-variable
        _oldrev, newrev, _refname = line.strip().split(" ")

        # Handle pushes
        if not app_path.exists():
            echo(f"-----> Creating app '{app}'", fg="green")
            app_path.mkdir()

            # The data directory may already exist, since this may be a full redeployment
            # (we never delete data since it may be expensive to recreate)
            data_path.mkdir(parents=True, exist_ok=True)

            cmd = f"git clone --quiet {app_obj.repo_path} {app}"
            subprocess.call(cmd, cwd=APP_ROOT, shell=True)

        do_deploy(app, newrev=newrev)


@hop3.command("git-receive-pack")
@argument("app")
def cmd_git_receive_pack(app: str) -> None:
    """INTERNAL: Handle git pushes for an app"""

    app = sanitize_app_name(app)
    hook_path = Path(GIT_ROOT, app, "hooks", "post-receive")

    if not hook_path.exists():
        hook_path.parent.mkdir(parents=True)

        # Initialize the repository with a hook to this script
        cmd = "git init --quiet --bare " + app
        subprocess.call(cmd, cwd=GIT_ROOT, shell=True)

        hook_path.write_text(
            dedent(
                f"""\
                #!/usr/bin/env bash
                set -e; set -o pipefail;
                cat | HOP3_ROOT="{HOP3_ROOT:s}" {HOP3_SCRIPT:s} git-hook {app:s}
                """,
            )
        )
        # Make the hook executable by our user
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR)

    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    cmd = 'git-shell -c "{}" '.format(sys.argv[1] + f" '{app}'")
    subprocess.call(cmd, cwd=GIT_ROOT, shell=True)


@hop3.command("git-upload-pack")
@argument("app")
def cmd_git_upload_pack(app: str) -> None:
    """INTERNAL: Handle git upload pack for an app"""
    app_obj = get_app(app)
    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    _cmd = sys.argv[1] + f" '{app_obj.name}'"
    cmd = f'git-shell -c "{_cmd}" '
    subprocess.call(cmd, cwd=GIT_ROOT, shell=True)
