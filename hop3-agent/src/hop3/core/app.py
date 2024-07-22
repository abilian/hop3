# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
import shutil
from pathlib import Path

from hop3.core.env import Env
from hop3.deploy import do_deploy
from hop3.run.spawn import spawn_app
from hop3.system.constants import (
    ACME_WWW,
    APP_ROOT,
    CACHE_ROOT,
    DATA_ROOT,
    ENV_ROOT,
    GIT_ROOT,
    LOG_ROOT,
    NGINX_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
)
from hop3.system.state import state
from hop3.util.console import Abort, log


def get_app(name: str) -> App:
    app = App(name)
    app.check_exists()
    return app


def list_apps() -> list[App]:
    return [App(name) for name in sorted(os.listdir(APP_ROOT))]


class App:
    """Represents a deployed app in the system."""

    name: str
    frozen: bool = False

    def __init__(self, name) -> None:
        self.name = name
        self.validate()
        self.frozen = True

    def __setattr__(self, key, value) -> None:
        if self.frozen:
            raise AttributeError("Cannot set attribute on frozen instance")
        super().__setattr__(key, value)

    def validate(self) -> None:
        for c in self.name:
            if not c.isalnum() and c not in {".", "_", "-"}:
                raise ValueError("Invalid app name")

    def check_exists(self) -> None:
        if not Path(APP_ROOT, self.name).exists():
            raise Abort(f"Error: app '{self.name}' not found.")

    @property
    def is_running(self) -> bool:
        return list(Path(UWSGI_ENABLED).glob(f"{self.name}*.ini")) != []

    # Paths

    @property
    def repo_path(self) -> Path:
        return Path(GIT_ROOT, self.name)

    @property
    def app_path(self) -> Path:
        return Path(APP_ROOT, self.name)

    @property
    def data_path(self) -> Path:
        return Path(DATA_ROOT, self.name)

    @property
    def virtualenv_path(self) -> Path:
        return Path(ENV_ROOT, self.name)

    def get_runtime_env(self) -> Env:
        return Env(state.get_app_env(self.name))

    # Actions
    def deploy(self) -> None:
        do_deploy(self.name)

    def destroy(self) -> None:
        # TODO: finish refactoring this method
        app = self.name

        # leave DATA_ROOT, since apps may create hard to reproduce data,
        # and CACHE_ROOT, since `nginx` will set permissions to protect it
        for root in [APP_ROOT, GIT_ROOT, ENV_ROOT, LOG_ROOT, CACHE_ROOT]:
            p = Path(root, app)
            if p.exists():
                log(f"Removing folder '{p}'", level=2, fg="blue")
                shutil.rmtree(p)

        for p in [UWSGI_AVAILABLE, UWSGI_ENABLED]:
            for f in Path(p).glob(f"{app}*.ini"):
                log(f"Removing file '{f}'", level=2, fg="blue")
                f.unlink()

        nginx_files = [
            Path(NGINX_ROOT, f"{app}.conf"),
            Path(NGINX_ROOT, f"{app}.sock"),
            Path(NGINX_ROOT, f"{app}.key"),
            Path(NGINX_ROOT, f"{app}.crt"),
        ]
        for f in nginx_files:
            if f.exists():
                log(f"Removing file '{f}'", level=2, fg="blue")
                f.unlink()

        acme_link = Path(ACME_WWW, app)
        acme_certs = acme_link.resolve()
        if acme_certs.exists():
            log(f"Removing folder '{acme_certs}'", level=2, fg="yellow")
            shutil.rmtree(acme_certs)

            log(f"Removing file '{acme_link}'", level=2, fg="yellow")
            os.unlink(acme_link)

        # We preserve data
        data_dir = Path(DATA_ROOT, app)
        if data_dir.exists():
            log(f"Preserving folder '{data_dir}'", level=2, fg="blue")

    def start(self) -> None:
        spawn_app(self.name)

    def stop(self) -> None:
        app_name = self.name
        config_files = list(UWSGI_ENABLED.glob(f"{app_name}*.ini"))

        if len(config_files) > 0:
            log(f"Stopping app '{app_name}'...", fg="blue")
            for c in config_files:
                c.unlink()
        else:
            # TODO app could be already stopped. Need to able to tell the difference.
            log(f"Error: app '{app_name}' not deployed!", fg="red")

    def restart(self) -> None:
        """Restart (or just start) a deployed app."""
        log(f"restarting app '{self.name}'...", fg="blue")
        self.stop()
        self.start()
