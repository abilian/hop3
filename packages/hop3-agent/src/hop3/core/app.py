# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shutil
from pathlib import Path

from attrs import frozen

from hop3.config.constants import (
    ACME_WWW,
    APP_ROOT,
    NGINX_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
)
from hop3.core.env import Env
from hop3.deploy import do_deploy
from hop3.run.spawn import spawn_app
from hop3.system.state import state
from hop3.util import Abort, log


def get_app(name: str, *, check: bool = True) -> App:
    """
    Retrieve an application instance by name, optionally checking its existence.

    Input:
        name (str): The name of the application to retrieve.
        check (bool, optional): Flag to indicate whether to check if the application exists. Defaults to True.

    Returns:
        App: An instance of the App class corresponding to the given name.

    Raises:
        ValueError: If 'check' is True and the application does not exist.
    """
    app = App(name)
    if check:
        app.check_exists()
    return app


def list_apps() -> list[App]:
    """
    Retrieve a list of applications from the APP_ROOT directory.

    Returns:
        list[App]: A list of App instances, each representing an application
                   located in the APP_ROOT directory.
    """
    return [App(name) for name in sorted(os.listdir(APP_ROOT))]


@frozen
class App:
    """Represents a deployed app in the system."""

    name: str

    def __attrs_post_init__(self) -> None:
        """
        Perform post-initialization validation.

        This is automatically called after the initialization of an instance, as part of the `attrs` library.
        It checks that the instance is in a valid state by invoking the `validate` method.

        Raises:
        - ValueError: in case validation fails.
        """
        self.validate()

    def validate(self) -> None:
        """
        Validates the name attribute of the class instance.

        Ensures that each character in the `name` attribute is either alphanumeric
        or one of the following allowed symbols: '.', '_', '-'.

        Raises:
            ValueError: If the `name` contains any characters other than alphanumeric characters,
                        '.', '_', or '-'.
        """
        for c in self.name:
            # Check if character is not alphanumeric and not in allowed symbols
            if not c.isalnum() and c not in {".", "_", "-"}:
                msg = "Invalid app name"
                raise ValueError(msg)

    def check_exists(self) -> None:
        if not (APP_ROOT / self.name).exists():
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
        return list(UWSGI_ENABLED.glob(f"{self.name}*.ini")) != []

    #
    # Paths
    #
    @property
    def app_path(self) -> Path:
        """Path to the root directory of the app."""
        return APP_ROOT / self.name

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
        """
        Retrieves the runtime environment for the current application.

        This fetches the environment settings for the application identified
        by the instance's name attribute.
        """
        return Env(state.get_app_env(self.name))

    # Actions
    def deploy(self) -> None:
        """
        Deploys the application by invoking the deployment process.

        This serves as a wrapper that calls the `do_deploy` function,
        which handles the actual deployment steps necessary for the application.
        """
        do_deploy(self)

    def destroy(self) -> None:
        """
        Remove various application-related files and directories, except for data.

        This deletes the application directory, repository directory,
        virtual environment, and log files associated with the application.
        It also removes UWSGI and NGINX configuration files and sockets.
        However, it preserves the application's data directory.
        """
        # TODO: finish refactoring this method
        app = self.name

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
        """
        Initiates the process to start an application by calling the spawn_app function.
        """
        spawn_app(self)

    def stop(self) -> None:
        """
        Stops the application by removing its configuration files if they exist.
        """
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
        """
        Restart (or just start) a deployed app.

        This stops and then starts the application, effectively restarting it.
        """
        log(f"restarting app '{self.name}'...", fg="blue")
        self.stop()
        self.start()
