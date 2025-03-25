# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Internal CLI commands to manage git hooks."""

from __future__ import annotations

import sys

from hop3.core.git import GitManager
from hop3.deploy import do_deploy
from hop3.lib import log, sanitize_app_name
from hop3.orm import App, AppRepository
from hop3.server.commands.registry import command


@command
class GitReceivePackCmd:
    """INTERNAL: Handle git pushes for an app."""

    name = "git-receive-pack"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app_name: str, db_session) -> None:
        app_name = sanitize_app_name(app_name)
        app_repo = AppRepository(session=db_session)
        app = app_repo.get_one_or_none(name=app_name)
        if not app:
            log(f"App {app_name} not found, creating it.")
            app = App(name=app_name)
            db_session.add(app)
        db_session.commit()

        git_manager = GitManager(app)
        git_manager.setup_hook()
        git_manager.receive_pack()
        db_session.commit()


@command
class GitUploadPackCmd:
    """INTERNAL: Handle git upload pack for an app."""

    name = "git-upload-pack"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app: App) -> None:
        git_manager = GitManager(app)
        git_manager.upload_pack()


@command
class GitHookCmd:
    """INTERNAL: Post-receive git hook."""

    name = "git-hook"
    hide = True

    def add_arguments(self, parser) -> None:
        parser.add_argument("app_name", type=str)

    def run(self, app_name: str, db_session) -> None:
        app_repo = AppRepository(session=db_session)
        app = app_repo.get_one_or_none(name=app_name)
        if not app:
            log(f"App {app_name} not found, creating it.")
            app = App(name=app_name)
            db_session.add(app)

        git_manager = GitManager(app)
        git_manager.clone()

        for line in sys.stdin:
            _oldrev, newrev, _refname = line.strip().split(" ")
            do_deploy(app, newrev=newrev)

        db_session.commit()
