# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import InstallingVirtualEnv, emit
from hop3.system.constants import UWSGI_ENABLED
from hop3.util import check_binaries
from hop3.util.backports import chdir
from hop3.util.console import Abort, log
from hop3.util.path import prepend_to_path

from .base import Builder


class NodeBuilder(Builder):
    """A builder class for creating Node projects.

    Attributes
    ----------
        name (str): The name of the builder.
        requirements (list): The list of required tools for building Node projects.

    Methods
    -------
        accept(): Check if the project meets the requirements for building Node projects.
        build(): Build the Node project by setting up the environment, installing Node, and installing modules.
        get_env(): Get the environment variables required for building the project.
        install_node(env): Install the specified version of Node using nodeenv.
        install_modules(env): Install the required npm modules for the project.

    """

    name = "Node"
    requirements = ["node", "npm"]

    # FIXME: should be more complex
    # check_requirements(["nodejs", "npm"])
    # or check_requirements(["node", "npm"])
    # or check_requirements(["nodeenv"])

    def accept(self):
        """Check if the package.json file exists in the specified app path.

        Returns
        -------
            bool: True if the package.json file exists, False otherwise.

        """
        return (self.app_path / "package.json").exists()

    def build(self) -> None:
        """Build the project environment.

        This method creates the necessary directories and installs the required dependencies for the project.
        """
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        with chdir(self.app_path):
            env = self.get_env()
            os.environ["PATH"] = str(env["PATH"])
            self.install_node(env)
            self.install_modules(env)

    def get_env(self) -> Env:
        """Get the environment variables for the application.

        Returns
        -------
            Env: An environment object containing the necessary variables for the application.

        """
        node_modules = self.app_path / "node_modules"
        npm_prefix = os.path.abspath(os.path.join(node_modules, ".."))
        path = prepend_to_path(
            [
                Path(self.virtual_env, "bin"),
                Path(node_modules, ".bin"),
            ],
        )
        env = Env(
            {
                "VIRTUAL_ENV": self.virtual_env,
                "NODE_PATH": node_modules,
                "NPM_CONFIG_PREFIX": npm_prefix,
                "PATH": path,
            },
        )
        env.parse_settings(self.env_file)
        return env

    def install_node(self, env: Env) -> None:
        """Install a specific version of Node.js using nodeenv.

        Args:
        ----
            env (dict): Dictionary containing environment variables, including 'NODE_VERSION' specifying the Node.js version to install.

        Raises:
        ------
            Abort: If trying to update Node.js while the application is running.

        """
        version = env.get("NODE_VERSION")
        node_binary = Path(self.virtual_env, "bin", "node")
        if node_binary.exists():
            completed_process = self.shell(f"{node_binary} -v", env=env)
            installed = completed_process.stdout.decode("utf8").rstrip("\n")
        else:
            installed = ""

        if version and check_binaries(["nodeenv"]):
            if not installed.endswith(version):
                started = list(Path(UWSGI_ENABLED).glob(f"{self.app_name}*.ini"))
                if installed and len(started):
                    msg = (
                        "Warning: Can't update node with app running. Stop the app &"
                        " retry."
                    )
                    raise Abort(msg)

                msg = "Installing node version '{NODE_VERSION:s}' using nodeenv".format(
                    **env,
                )
                log(msg, level=5, fg="green")
                cmd = (
                    "nodeenv --prebuilt --node={NODE_VERSION:s} --clean-src --force"
                    " {VIRTUAL_ENV:s}".format(**env)
                )
                self.shell(cmd, cwd=self.virtual_env, env=env)
            else:
                log(f"Node is installed at {version}.", level=5, fg="green")

    def install_modules(self, env: Env) -> None:
        """Install necessary modules for the application using npm.

        Args:
        ----
            self: The instance of the class.
            env (dict): Environment variables to be passed to the shell.

        """
        emit(InstallingVirtualEnv(self.app_name))

        npm_prefix = self.app_path
        package_json = self.app_path / "package.json"

        assert package_json.exists()
        assert check_binaries(["npm"])

        cmd = f"npm install --prefix {npm_prefix} --package-lock=false"
        self.shell(cmd, env=env)
