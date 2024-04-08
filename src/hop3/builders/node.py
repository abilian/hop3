# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.events import InstallingVirtualEnv, emit
from hop3.system.constants import UWSGI_ENABLED
from hop3.util import check_binaries, shell
from hop3.util.backports import chdir
from hop3.util.console import Abort, log
from hop3.util.path import prepend_to_path
from hop3.util.settings import parse_settings

from .base import Builder


class NodeBuilder(Builder):
    name = "Node"
    requirements = ["node", "npm"]

    # FIXME: should be more complex
    # check_requirements(["nodejs", "npm"])
    # or check_requirements(["node", "npm"])
    # or check_requirements(["nodeenv"])

    def accept(self):
        return (self.app_path / "package.json").exists()

    def build(self) -> None:
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        with chdir(self.app_path):
            env = self.get_env()
            os.environ["PATH"] = str(env["PATH"])
            self.install_node(env)
            self.install_modules(env)

    def get_env(self) -> dict:
        node_modules = self.app_path / "node_modules"
        npm_prefix = os.path.abspath(os.path.join(node_modules, ".."))
        path = prepend_to_path(
            [
                Path(self.virtual_env, "bin"),
                Path(node_modules, ".bin"),
            ]
        )
        env = {
            "VIRTUAL_ENV": self.virtual_env,
            "NODE_PATH": node_modules,
            "NPM_CONFIG_PREFIX": npm_prefix,
            "PATH": path,
        }

        if (env_file := Path("ENV")).exists():
            env.update(parse_settings(env_file, env))
        return env

    def install_node(self, env) -> None:
        version = env.get("NODE_VERSION")
        node_binary = Path(self.virtual_env, "bin", "node")
        if node_binary.exists():
            installed = (
                self.shell(f"{node_binary} -v", env=env).decode("utf8").rstrip("\n")
            )
        else:
            installed = ""

        if version and check_binaries(["nodeenv"]):
            if not installed.endswith(version):
                started = list(Path(UWSGI_ENABLED).glob(f"{self.app_name}*.ini"))
                if installed and len(started):
                    raise Abort(
                        "Warning: Can't update node with app running. Stop the app & retry.",
                    )

                log(
                    "Installing node version '{NODE_VERSION:s}' using nodeenv".format(
                        **env
                    ),
                    level=5,
                    fg="green",
                )
                shell(
                    "nodeenv --prebuilt --node={NODE_VERSION:s} --clean-src --force {VIRTUAL_ENV:s}".format(
                        **env
                    ),
                    cwd=self.virtual_env,
                    env=env,
                )
            else:
                log(f"Node is installed at {version}.", level=5, fg="green")

    def install_modules(self, env) -> None:
        emit(InstallingVirtualEnv(self.app_name))

        npm_prefix = self.app_path
        package_json = self.app_path / "package.json"

        assert package_json.exists()
        assert check_binaries(["npm"])

        self.shell(
            f"npm install --prefix {npm_prefix} --package-lock=false",
            env=env,
        )
