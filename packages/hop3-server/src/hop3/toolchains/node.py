# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Node projects."""

from __future__ import annotations

from hop3 import config as c
from hop3.core.env import Env
from hop3.core.events import InstallingVirtualEnv, emit
from hop3.core.protocols import BuildArtifact
from hop3.lib import Abort, chdir, check_binaries, log, prepend_to_path

from ._base import LanguageToolchain


class NodeToolchain(LanguageToolchain):
    """Language toolchain for Node projects."""

    name = "Node"
    requirements = ["node", "npm"]  # noqa: RUF012

    # FIXME: should be more complex
    # check_requirements(["nodejs", "npm"])
    # or check_requirements(["node", "npm"])
    # or check_requirements(["nodeenv"])

    def accept(self) -> bool:
        """Check if the package.json file exists in the specified app path."""
        return self.check_exists("package.json")

    def build(self) -> BuildArtifact:
        """Build the project environment.

        This creates the necessary directories and installs the required
        dependencies for the project.
        """
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        with chdir(self.src_path):
            env = self.get_env()
            self.install_node(env)
            self.install_modules(env)

        return BuildArtifact(
            kind="node",
            location=str(self.virtual_env),
            metadata={
                "node_modules": str(self.src_path / "node_modules"),
                "app_name": self.app_name,
            },
        )

    def get_env(self) -> Env:
        """Get the environment variables for the application.

        Returns
        -------
            Env: An environment object containing the necessary variables for the application.
        """
        node_modules = self.src_path / "node_modules"
        # npm_prefix = os.path.abspath(os.path.join(node_modules, ".."))
        npm_prefix = node_modules.parent.absolute()
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                node_modules / ".bin",
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

        This checks if the specified Node.js version is installed in the
        virtual environment. If not, and the `nodeenv` binary is available, it will
        attempt to install the specified Node.js version. If the application is
        running, it raises an exception to prevent an update during runtime.

        Args:
        ----
            env (Env): Dictionary containing environment variables, including
            'NODE_VERSION' specifying the Node.js version to install.

        Raises:
        ------
            Abort: If trying to update Node.js while the application is running.
        """
        version = env.get("NODE_VERSION")
        node_binary = self.virtual_env / "bin" / "node"
        if node_binary.exists():
            completed_process = self.shell(f"{node_binary} -v", env=env)
            installed = completed_process.stdout.decode("utf8").rstrip("\n")
        else:
            installed = ""

        # Check if the specified version is different from the installed one and if nodeenv is available
        if version and check_binaries(["nodeenv"]):
            if not installed.endswith(version):
                started = list(c.UWSGI_ENABLED.glob(f"{self.app_name}*.ini"))

                if installed and started:
                    # Raise an error if the app is running
                    msg = (
                        "Warning: Can't update node with app running. Stop the app &"
                        " retry."
                    )
                    raise Abort(msg)

                # Log installation of the specified node version using nodeenv
                log(
                    f"Installing node version '{version}' using nodeenv",
                    level=3,
                    fg="green",
                )
                cmd = f"nodeenv --prebuilt --node={version} --clean-src --force {self.virtual_env}"
                self.shell(cmd, cwd=self.virtual_env, env=env)
            else:
                log(f"Node is installed at {version}.", level=3, fg="green")

    def install_modules(self, env: Env) -> None:
        """Install necessary modules for the application using npm.

        This uses npm to install the dependencies listed in the
        'package.json' file located at the specified source path. It
        ensures that npm is available and executes the installation
        command while passing the provided environment variables.
        """
        emit(InstallingVirtualEnv(self.app_name))

        npm_prefix = self.src_path
        package_json = self.src_path / "package.json"

        assert package_json.exists()
        assert check_binaries(["npm"])

        cmd = f"npm install --prefix {npm_prefix} --package-lock=false"
        self.shell(cmd, env=env)
