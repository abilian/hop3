# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
import stat
import subprocess
import sys
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

    for line in sys.stdin:
        # pylint: disable=unused-variable
        _oldrev, newrev, _refname = line.strip().split(" ")

        # Handle pushes
        if not os.path.exists(app_obj.app_path):
            echo(f"-----> Creating app '{app}'", fg="green")
            os.makedirs(app_obj.app_path)
            # The data directory may already exist, since this may be a full redeployment
            # (we never delete data since it may be expensive to recreate)
            if not os.path.exists(app_obj.data_path):
                os.makedirs(app_obj.data_path)

            subprocess.call(
                f"git clone --quiet {app_obj.repo_path} {app}",
                cwd=APP_ROOT,
                shell=True,
            )

        do_deploy(app, newrev=newrev)


@hop3.command("git-receive-pack")
@argument("app")
def cmd_git_receive_pack(app: str) -> None:
    """INTERNAL: Handle git pushes for an app"""

    app = sanitize_app_name(app)
    hook_path = os.path.join(GIT_ROOT, app, "hooks", "post-receive")

    env = globals()
    env.update(locals())

    env = {
        "HOP3_ROOT": HOP3_ROOT,
        "HOP3_SCRIPT": HOP3_SCRIPT,
        "app": app,
    }

    if not os.path.exists(hook_path):
        os.makedirs(os.path.dirname(hook_path))
        # Initialize the repository with a hook to this script
        subprocess.call("git init --quiet --bare " + app, cwd=GIT_ROOT, shell=True)
        with open(hook_path, "w") as h:
            h.write(
                dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -e; set -o pipefail;
                    cat | HOP3_ROOT="{HOP3_ROOT:s}" {HOP3_SCRIPT:s} git-hook {app:s}
                    """,
                ),
            )
        # Make the hook executable by our user
        os.chmod(hook_path, os.stat(hook_path).st_mode | stat.S_IXUSR)

    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    subprocess.call(
        'git-shell -c "{}" '.format(sys.argv[1] + f" '{app}'"),
        cwd=GIT_ROOT,
        shell=True,
    )


@hop3.command("git-upload-pack")
@argument("app")
def cmd_git_upload_pack(app: str) -> None:
    """INTERNAL: Handle git upload pack for an app"""
    app_obj = get_app(app)
    env = globals()
    env.update(locals())
    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    cmd = 'git-shell -c "{}" '.format(sys.argv[1] + f" '{app}'")
    subprocess.call(cmd, cwd=GIT_ROOT, shell=True)
