# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests
from jsonrpcclient import Error, parse, request

from .util import run_command

if TYPE_CHECKING:
    from .config import Config
    from .state import State


# TODO: use State


class Client:
    config: Config
    state: State | None

    def __init__(self, config: Config, state: State | None):
        self.config = config
        self.state = state

        # Define variables
        git_remote = run_command("git config --get remote.hop3.url")
        hop3_server = os.environ.get("HOP3_SERVER")
        hop3_app = os.environ.get("HOP3_APP")
        self.remote = git_remote or f"{hop3_server}:{hop3_app}"

    def get_host(self):
        # TEMP
        return "localhost"
        # return self.config["host"]

    def get_port(self):
        # TEMP
        return 8000
        # return self.config["port"]

    def rpc(self, method, *args):
        """Call a remote method"""
        url = f"http://{self.get_host()}:{self.get_port()}/rpc"
        json_request = request(method, args)
        response = requests.post(
            url,
            json=json_request,
            verify=False,
            # cert="../hop3-server/ssl/cert.pem",
        )
        try:
            response.raise_for_status()
            return parse(response.json())
        except Exception as e:
            return Error(response.status_code, str(e), "", json_request["id"])
