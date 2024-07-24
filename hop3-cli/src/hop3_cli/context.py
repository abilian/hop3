from dataclasses import dataclass, field

import rpyc

from .config import Config
from .state import State

# TODO: use State


@dataclass
class Context:
    config: Config
    state: State | None

    _cache: dict = field(default_factory=dict, repr=False)

    def get_host(self):
        return self.config.get("host")

    def get_port(self):
        return self.config.get("port")

    def get_client(self):
        """Get the client instance"""
        if "client" in self._cache:
            return self._cache["client"]
        client = rpyc.connect(self.get_host(), self.get_port())
        self._cache["client"] = client
        return client

    def rpc(self, service, method, *args, **kwargs):
        """Call a remote method"""
        client = self.get_client()
        return client.root.call(service, method, *args, **kwargs)
