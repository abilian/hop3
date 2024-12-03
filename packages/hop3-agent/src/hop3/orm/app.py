# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hop3.config import c
from hop3.core.env import Env
from hop3.deploy import do_deploy
from hop3.run.spawn import spawn_app
from hop3.util import Abort, log

if TYPE_CHECKING:
    from .env import EnvVar


class AppStateEnum(Enum):
    """Enumeration for representing the state of an application.

    The state of an application can be RUNNING, STOPPED, or PAUSED.
    """

    RUNNING = 1
    STOPPED = 2
    PAUSED = 3
    # ...


class App(BigIntAuditBase):
    """Represents an application with relevant properties such as name, run
    state, and port."""

    __tablename__ = "app"

    name: Mapped[str] = mapped_column(String(128))
    run_state: Mapped[AppStateEnum] = mapped_column(default=AppStateEnum.STOPPED)
    port: Mapped[int] = mapped_column(default=0)
    hostname: Mapped[str] = mapped_column(default="")

    env_vars: Mapped[list[EnvVar]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )

    def check_exists(self) -> None:
        if not (c.APP_ROOT / self.name).exists():
            msg = f"Error: app '{self.name}' not found."
            raise Abort(msg)

    def create(self) -> None:
        self.app_path.mkdir(exist_ok=True)
        # The data directory may already exist, since this may be
        # a full redeployment
        # (we never delete data since it may be expensive to recreate)
        for path in [self.repo_path, self.src_path, self.data_path, self.log_path]:
            path.mkdir(exist_ok=True)

        # log_path = LOG_ROOT / self.app_name
        # if not log_path.exists():
        #     os.makedirs(log_path)

    @property
    def is_running(self) -> bool:
        return self.run_state == AppStateEnum.RUNNING

    #
    # Paths
    #
    @property
    def app_path(self) -> Path:
        """Path to the root directory of the app."""
        return c.APP_ROOT / self.name

    @property
    def repo_path(self) -> Path:
        """Path to the git repository of the app."""
        return self.app_path / "git"

    @property
    def src_path(self) -> Path:
        """Path to the source directory of the app."""
        return self.app_path / "src"

    @property
    def data_path(self) -> Path:
        """Path to the data directory of the app."""
        return self.app_path / "data"

    @property
    def log_path(self) -> Path:
        """Path to the log directory of the app."""
        return self.app_path / "log"

    @property
    def virtualenv_path(self) -> Path:
        """Pathe to the virtualenv of the app."""
        return self.app_path / "venv"

    def get_runtime_env(self) -> Env:
        """Retrieves the runtime environment for the current application.

        This fetches the environment settings for the application
        identified by the instance's name attribute.
        """
        data = {}
        for env_var in self.env_vars:
            data[env_var.name] = env_var.value
        return Env(data)

    def update_runtime_env(self, env: Env) -> None:
        """Updates the runtime environment for the current application.

        This updates the environment settings for the application
        identified by the instance's name attribute.
        """
        from .env import EnvVar

        self.env_vars.clear()
        for key, value in env.items():
            self.env_vars.append(EnvVar(name=key, value=value, app=self))

    #
    # Actions
    #
    def deploy(self) -> None:
        """Deploys the application by invoking the deployment process.

        This serves as a wrapper that calls the `do_deploy` function,
        which handles the actual deployment steps necessary for the application.
        """
        do_deploy(self)

    def destroy(self) -> None:
        """Remove various application-related files and directories, except for
        data.

        This deletes the application directory, repository directory,
        virtual environment, and log files associated with the
        application. It also removes UWSGI and NGINX configuration files
        and sockets. However, it preserves the application's data
        directory.
        """
        # TODO: finish refactoring this method
        app_name = self.name

        def remove_file(p: Path) -> None:
            # Remove the file or directory at the given path if it exists.
            if p.exists():
                if p.is_dir():
                    log(f"Removing directory '{p}'", level=2, fg="blue")
                    shutil.rmtree(p)  # Recursively remove a directory tree
                else:
                    log(f"Removing file '{p}'", level=2, fg="blue")
                    p.unlink()  # Remove a file

        # Leave DATA_ROOT, as apps may create hard-to-reproduce data,
        # and CACHE_ROOT, as `nginx` will set permissions to protect it
        remove_file(self.app_path)
        remove_file(self.repo_path)
        remove_file(self.virtualenv_path)
        remove_file(self.log_path)

        for p in [c.UWSGI_AVAILABLE, c.UWSGI_ENABLED]:
            for f in Path(p).glob(f"{app_name}*.ini"):
                remove_file(f)

        remove_file(c.NGINX_ROOT / f"{app_name}.conf")
        remove_file(c.NGINX_ROOT / f"{app_name}.sock")
        remove_file(c.NGINX_ROOT / f"{app_name}.key")
        remove_file(c.NGINX_ROOT / f"{app_name}.crt")

        acme_link = Path(c.ACME_WWW, app_name)
        acme_certs = acme_link.resolve()
        remove_file(acme_link)
        remove_file(acme_certs)

        # We preserve data
        data_dir = self.data_path
        if data_dir.exists():
            log(f"Preserving folder '{data_dir}'", level=2, fg="blue")

    def start(self) -> None:
        """Initiates the process to start an application by calling the
        spawn_app function."""
        self.run_state = AppStateEnum.RUNNING
        spawn_app(self)

    def stop(self) -> None:
        """Stops the application by removing its configuration files if they
        exist."""
        self.run_state = AppStateEnum.STOPPED

        app_name = self.name
        config_files = list(c.UWSGI_ENABLED.glob(f"{app_name}*.ini"))

        if len(config_files) > 0:
            log(f"Stopping app '{app_name}'...", fg="blue")
            for config_file in config_files:
                config_file.unlink()
        else:
            # TODO app could be already stopped. Need to able to tell the difference.
            log(f"Error: app '{app_name}' not deployed!", fg="red")

    def restart(self) -> None:
        """Restart (or just start) a deployed app.

        This stops and then starts the application, effectively
        restarting it.
        """
        log(f"restarting app '{self.name}'...", fg="blue")
        self.stop()
        self.start()
