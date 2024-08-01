# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from dataclasses import dataclass

import requests
from jsonrpcclient import parse, request

from .config import Config
from .state import State

# TODO: use State


@dataclass
class Context:
    config: Config
    state: State | None

    def get_host(self):
        return self.config["host"]

    def get_port(self):
        return self.config["port"]

    def rpc(self, method, *args):
        """Call a remote method"""
        url = f"https://{self.get_host()}:{self.get_port()}/rpc"
        json_request = request(method, args)
        response = requests.post(
            url,
            json=json_request,
            verify=False,
            # cert="../hop3-server/ssl/cert.pem",
        )
        json_response = response.json()
        return parse(json_response)
