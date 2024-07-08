# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: E402

from __future__ import annotations

import shutil
import subprocess
import time
import traceback
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx
from devtools import debug
from httpcore import ConnectError

from hop3.util.backports import chdir

from .common import DOMAIN, SERVER, run

DEFAULT_WAIT = 10
CLOJURE_WAIT = 15


class TestSession:
    def __init__(self, app_directory: Path, config: dict) -> None:
        debug(f"Testing {app_directory.absolute()}")
        assert app_directory.exists(), f"{app_directory} does not exist"
        assert app_directory.is_dir(), f"{app_directory} is not a directory"

        self.directory = app_directory
        self.name = app_directory.name
        self.app_name = f"{self.name}-{int(time.time())}"
        self.app_host_name = f"{self.app_name}.{DOMAIN}"
        self.config = config or {}

    def run(self) -> str:
        try:
            self.deploy_app()
            time.sleep(5)
            self.test_all_commands()
            if self.config.get("keep", False):
                print(f"Keeping {self.app_name}")
            else:
                self.cleanup()
        except Exception as e:
            traceback.print_exc()
            print(f"Error testing {self.app_name}: {e}")
            return "error"

        return "success"

    def test_all_commands(self) -> None:
        self.test_apps_command()
        self.test_web()

    def test_web(self):
        self.hop("config:set", f"NGINX_SERVER_NAME={self.app_host_name}")
        if self.app_name.startswith("clojure"):
            time.sleep(CLOJURE_WAIT)
        else:
            time.sleep(DEFAULT_WAIT)

        self.check_app_is_up()

    def test_apps_command(self):
        time.sleep(DEFAULT_WAIT)
        result = self.hop("apps")
        assert self.app_name in result, f"App {self.app_name} not found in {result}"

    def cleanup(self) -> None:
        self.hop("destroy")
        time.sleep(5)
        # check_app_is_down()

    def hop(self, cmd, args=""):
        if cmd == "apps":
            shell_cmd = f"ssh hop3@{SERVER} {cmd}"
        else:
            shell_cmd = f"ssh hop3@{SERVER} {cmd} {self.app_name}"
        if args:
            shell_cmd += f" {args}"
        return run(shell_cmd)

    @property
    def app_url(self) -> str:
        return f"https://{self.app_host_name}/"

    def check_app_is_up(self) -> None:
        url = self.app_url
        response = None
        for i in range(1, 6):
            try:
                response = httpx.get(url, verify=False)
            except ConnectError:
                time.sleep(i)
                continue
            except OSError as e:
                raise AssertionError(
                    f"App {self.app_host_name} ({url}) is not up, got OSError:\n{e}",
                )

        if response is None:
            raise AssertionError(
                f"App {self.app_host_name} ({url}) is not up, can't connect to it",
            )
        if response.status_code != HTTPStatus.OK:
            raise AssertionError(
                f"App {self.app_host_name} ({url}) is not up, got status code"
                f" {response.status_code}",
            )

        self.check_app_content()

    def check_app_content(self):
        check_script_path = self.directory / "check.py"
        if check_script_path.exists():
            print("Checking app content")
            ctx: dict[str, Any] = {}
            exec(check_script_path.read_text(), ctx)
            result = ctx["check"](self.app_host_name)
            debug(result)

    def check_app_is_down(self) -> None:
        url = self.app_url
        result = httpx.get(url, verify=False)
        assert result.status_code == HTTPStatus.BAD_GATEWAY

    def get_all_apps(self) -> Iterator:
        cmd = f"ssh hop3@{SERVER} apps"
        p = subprocess.run(cmd, shell=True, capture_output=True, check=True)
        lines = p.stdout.decode().split("\n")
        for line in lines:
            if line.strip().startswith("*"):
                yield line.strip().split()[1]

    def deploy_app(self) -> None:
        print(Path.cwd())

        tmp_dir = Path("tmp", f"{self.name}-example")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.copytree(f"{self.directory}", tmp_dir)

        with chdir(tmp_dir):
            run("git init")
            run("git add .")
            run("git commit -m 'init'")
            run(f"git remote add hop3 hop3@{SERVER}:{self.app_name}")
            run("git push hop3 main")
