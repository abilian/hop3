# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shutil
from pathlib import Path

from attrs import frozen

from hop3.core.env import Env
from hop3.deploy import do_deploy
from hop3.run.spawn import spawn_app
from hop3.system.constants import (
    ACME_WWW,
    APP_ROOT,
    DATA_ROOT,
    ENV_ROOT,
    GIT_ROOT,
    LOG_ROOT,
    NGINX_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
)
from hop3.system.state import state
from hop3.util import Abort, log


def get_app(name: str, *, check: bool = True) -> App:
    app = App(name)
    if check:
        app.check_exists()
    return app


def list_apps() -> list[App]:
    return [App(name) for name in sorted(os.listdir(APP_ROOT))]


@frozen
class App:
    """Represents a deployed app in the system."""

    name: str

    def __attrs_post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for c in self.name:
            if not c.isalnum() and c not in {".", "_", "-"}:
                raise ValueError("Invalid app name")

    def check_exists(self) -> None:
        if not (APP_ROOT / self.name).exists():
            raise Abort(f"Error: app '{self.name}' not found.")

    def create(self) -> None:
        self.app_path.mkdir(exist_ok=True)
        # The data directory may already exist, since this may be a full redeployment
        # (we never delete data since it may be expensive to recreate)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.log_path.mkdir(parents=True, exist_ok=True)
        # log_path = LOG_ROOT / self.app_name
        # if not log_path.exists():
        #     os.makedirs(log_path)

    @property
    def is_running(self) -> bool:
        return list(UWSGI_ENABLED.glob(f"{self.name}*.ini")) != []

    # Paths

    @property
    def repo_path(self) -> Path:
        return GIT_ROOT / self.name

    @property
    def app_path(self) -> Path:
        return APP_ROOT / self.name

    @property
    def data_path(self) -> Path:
        return DATA_ROOT / self.name

    @property
    def log_path(self) -> Path:
        return LOG_ROOT / self.name

    @property
    def virtualenv_path(self) -> Path:
        return ENV_ROOT / self.name

    def get_runtime_env(self) -> Env:
        return Env(state.get_app_env(self.name))

    # Actions
    def deploy(self) -> None:
        do_deploy(self)

    def destroy(self) -> None:
        # TODO: finish refactoring this method
        app = self.name

        def remove_file(p: Path) -> None:
            if p.exists():
                if p.is_dir():
                    log(f"Removing folder '{p}'", level=2, fg="blue")
                    shutil.rmtree(p)
                else:
                    log(f"Removing file '{p}'", level=2, fg="blue")
                    os.unlink(p)

        # leave DATA_ROOT, since apps may create hard to reproduce data,
        # and CACHE_ROOT, since `nginx` will set permissions to protect it
        remove_file(self.app_path)
        remove_file(self.repo_path)
        remove_file(self.virtualenv_path)
        remove_file(self.log_path)

        for p in [UWSGI_AVAILABLE, UWSGI_ENABLED]:
            for f in Path(p).glob(f"{app}*.ini"):
                remove_file(f)

        remove_file(NGINX_ROOT / f"{app}.conf")
        remove_file(NGINX_ROOT / f"{app}.sock")
        remove_file(NGINX_ROOT / f"{app}.key")
        remove_file(NGINX_ROOT / f"{app}.crt")

        acme_link = Path(ACME_WWW, app)
        acme_certs = acme_link.resolve()
        remove_file(acme_link)
        remove_file(acme_certs)

        # We preserve data
        data_dir = self.data_path
        if data_dir.exists():
            log(f"Preserving folder '{data_dir}'", level=2, fg="blue")

    def start(self) -> None:
        spawn_app(self)

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
