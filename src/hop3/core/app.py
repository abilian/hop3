# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
import shutil
from glob import glob
from pathlib import Path

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
from hop3.util.console import Abort, log
from hop3.util.settings import parse_settings


def get_app(name: str) -> App:
    app = App(name)
    app.check_exists()
    return app


def list_apps() -> list[App]:
    return [App(name) for name in os.listdir(APP_ROOT)]


class App:
    """Represents a deployed app in the system."""

    name: str
    frozen: bool = False

    def __init__(self, name) -> None:
        self.name = name
        self.validate()
        self.frozen = True

    def __setattr__(self, key, value):
        if self.frozen:
            raise AttributeError("Cannot set attribute on frozen instance")
        super().__setattr__(key, value)

    def validate(self) -> None:
        for c in self.name:
            if not c.isalnum() and c not in (".", "_", "-"):
                raise ValueError("Invalid app name")

    def check_exists(self) -> None:
        if not Path(APP_ROOT, self.name).exists():
            raise Abort(f"Error: app '{self.name}' not found.")

    @property
    def is_running(self) -> bool:
        return list(Path(UWSGI_ENABLED).glob(f"{self.name}*.ini")) != []

    # Paths

    @property
    def repo_path(self) -> str:
        return os.path.join(GIT_ROOT, self.name)

    @property
    def app_path(self) -> str:
        return os.path.join(APP_ROOT, self.name)

    @property
    def data_path(self) -> str:
        return os.path.join(DATA_ROOT, self.name)

    @property
    def env_path(self) -> str:
        return os.path.join(ENV_ROOT, self.name)

    @property
    def _env_file_path(self) -> Path:
        return Path(self.env_path, "LIVE_ENV")

    def get_runtime_env(self) -> dict:
        if not self._env_file_path.exists():
            return {}
        return parse_settings(self._env_file_path)

    # Actions
    def deploy(self) -> None:
        do_deploy(self.name)

    def destroy(self) -> None:
        # TODO: finish refactoring this method
        app = self.name

        # leave DATA_ROOT, since apps may create hard to reproduce data,
        # and CACHE_ROOT, since `nginx` will set permissions to protect it
        for p in [
            os.path.join(x, app)
            for x in [APP_ROOT, GIT_ROOT, ENV_ROOT, LOG_ROOT, CACHE_ROOT]
        ]:
            if os.path.exists(p):
                log(f"Removing folder '{p}'", level=2, fg="blue")
                shutil.rmtree(p)

        for p in [
            os.path.join(x, f"{app}*.ini") for x in [UWSGI_AVAILABLE, UWSGI_ENABLED]
        ]:
            g = glob(p)
            if len(g) > 0:
                for f in g:
                    log(f"Removing file '{f}'", level=2, fg="blue")
                    os.remove(f)

        nginx_files = [
            os.path.join(NGINX_ROOT, f"{app}.{x}")
            for x in ["conf", "sock", "key", "crt"]
        ]
        for f in nginx_files:
            if os.path.exists(f):
                log(f"Removing file '{f}'", level=2, fg="blue")
                os.remove(f)

        acme_link = os.path.join(ACME_WWW, app)
        acme_certs = os.path.realpath(acme_link)
        if os.path.exists(acme_certs):
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
        config = glob(os.path.join(UWSGI_ENABLED, f"{app_name}*.ini"))

        if len(config) > 0:
            log(f"Stopping app '{app_name}'...", fg="blue")
            for c in config:
                os.remove(c)
        else:
            # TODO app could be already stopped. Need to able to tell the difference.
            log(f"Error: app '{app_name}' not deployed!", fg="red")

    def restart(self) -> None:
        """Restart (or just start) a deployed app"""
        log(f"restarting app '{self.name}'...", fg="blue")
        self.stop()
        self.start()
