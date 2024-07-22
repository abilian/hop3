# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

from hop3.core.env import Env
from hop3.system.constants import APP_ROOT, ENV_ROOT
from hop3.util import shell


class Builder:
    """A class representing a builder for an application.

    Attributes
    ----------
        app_name (str): The name of the application being built.
        requirements (ClassVar[list[str]]): The list of requirements needed for building the application.
        name (ClassVar[str]): Name of the class.

    Methods
    -------
        __init__(self, app_name: str) -> None: Constructor method for the Builder class.
        accept(self) -> bool: Method to accept a build request.
        build(self) -> None: Method to build the application.
        app_path(self) -> Path: Property method to get the path of the application.
        virtual_env(self) -> Path: Property method to get the virtual environment path.
        env_file(self) -> Path: Property method to get the environment file path.
        shell(self, command: str, cwd: str | Path='', **kwargs) -> None: Method to run a shell command.
        get_env(self) -> Env: Method to get the environment settings for the application.

    """

    app_name: str

    # Class attitutes
    requirements: ClassVar[list[str]]
    name: ClassVar[str]

    def __init__(self, app_name: str) -> None:
        """Initialize the class with the specified app name.

        Args:
        ----
            app_name (str): The name of the application.

        Returns:
        -------
            None

        Raises:
        ------
            N/A

        """
        self.app_name = app_name

    def accept(self) -> bool:
        """Accepts the input specified by the subclass.

        Returns
        -------
            bool: The result of the specific implementation in the subclass.

        Raises
        ------
            NotImplementedError: This method must be implemented in the subclass.

        """
        raise NotImplementedError

    def build(self) -> None:
        """Build function not implemented.

        Raises
        ------
            NotImplementedError: This method is not implemented and should be overridden by subclasses.

        """
        raise NotImplementedError

    @property
    def app_path(self) -> Path:
        """Property method for determining the application path.

        Returns
        -------
            Path: The path to the application directory.

        """
        return Path(APP_ROOT, self.app_name)

    @property
    def virtual_env(self) -> Path:
        """Get the virtual environment path for the application.

        Returns
        -------
            Path: The path to the virtual environment for the current application.

        """
        return Path(ENV_ROOT, self.app_name)

    @property
    def env_file(self) -> Path:
        """Return the path to the environment file for the application.

        Returns
        -------
            Path: The path to the environment file for the application.

        """
        return Path(APP_ROOT, self.app_name, "ENV")

    def shell(
        self, command: str, cwd: str | Path = "", **kwargs
    ) -> subprocess.CompletedProcess:
        """Run a shell command with optional working directory and additional
        keyword arguments.

        Args:
        ----
            command (str): The shell command to be executed.
            cwd (str or Path, optional): The working directory where the command will be executed.
                Defaults to the application path if not provided.
            **kwargs: Additional keyword arguments to be passed to the shell function.

        """
        if not cwd:
            cwd = str(self.app_path)
        return shell(command, cwd=str(cwd), **kwargs)

    def get_env(self) -> Env:
        """Get the environment settings from a file and return an Env object.

        Returns
        -------
            Env: An Env object containing the parsed settings.

        Raises
        ------
            FileNotFoundError: If the specified environment file is not found.

        """
        env = Env()
        env.parse_settings(self.env_file)
        return env
