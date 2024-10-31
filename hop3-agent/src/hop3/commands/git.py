# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Internal CLI commands to manage git hooks."""

from __future__ import annotations

import sys

from click import argument

from hop3.core.app import App, get_app
from hop3.core.git import GitManager
from hop3.deploy import do_deploy
from hop3.util import sanitize_app_name

from .cli import hop3


@hop3.command("git-receive-pack")
@argument("app_name")
def cmd_git_receive_pack(app_name: str) -> None:
    """INTERNAL: Handle git pushes for an app."""
    app_name = sanitize_app_name(app_name)
    app = get_app(app_name, check=False)

    git_manager = GitManager(app)
    git_manager.setup_hook()
    git_manager.receive_pack()


@hop3.command("git-upload-pack")
@argument("app_name")
def cmd_git_upload_pack(app_name: str) -> None:
    """INTERNAL: Handle git upload pack for an app."""
    app = get_app(app_name)
    git_manager = GitManager(app)
    git_manager.upload_pack()


@hop3.command("git-hook")
@argument("app_name")
def cmd_git_hook(app_name: str) -> None:
    """INTERNAL: Post-receive git hook."""
    app = App(app_name)
    git_manager = GitManager(app)
    git_manager.clone()

    for line in sys.stdin:
        _oldrev, newrev, _refname = line.strip().split(" ")
        do_deploy(app, newrev=newrev)
