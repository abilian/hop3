# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Internal CLI commands to manage git hooks."""

from __future__ import annotations

import sys

from hop3.core.app import App, get_app
from hop3.core.git import GitManager
from hop3.deploy import do_deploy
from hop3.util import sanitize_app_name

from .base import command


@command
class GitReceivePackCmd:
    """INTERNAL: Handle git pushes for an app."""

    name = "git-receive-pack"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app_name: str) -> None:
        app_name = sanitize_app_name(app_name)
        app = get_app(app_name, check=False)

        git_manager = GitManager(app)
        git_manager.setup_hook()
        git_manager.receive_pack()


@command
class GitUploadPackCmd:
    """INTERNAL: Handle git upload pack for an app."""

    name = "git-upload-pack"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app_name: str) -> None:
        app = get_app(app_name)
        git_manager = GitManager(app)
        git_manager.upload_pack()


@command
class GitHookCmd:
    """INTERNAL: Post-receive git hook."""

    name = "git-hook"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app_name: str) -> None:
        app = App(app_name)
        git_manager = GitManager(app)
        git_manager.clone()

        for line in sys.stdin:
            _oldrev, newrev, _refname = line.strip().split(" ")
            do_deploy(app, newrev=newrev)
