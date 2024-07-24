from __future__ import annotations

import argparse
import dataclasses
from abc import ABCMeta, abstractmethod
from typing import Any, Sequence, ClassVar

import rpyc


__all__ = ['Command']


@dataclasses.dataclass(frozen=True)
class Command(metaclass=ABCMeta):
    # The command name
    name: ClassVar[str]

    # The command help
    help: ClassVar[str] = ""

    # Description of the command arguments
    args: ClassVar[Sequence[dict[str, Any]]] = ()

    _cache: dict = dataclasses.field(default_factory=dict, repr=False)

    def setup(self, parser, subparsers):
        help = self.__doc__ or self.help

        subparser = subparsers.add_parser(
            self.name,
            help=help,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        self.setup_common_arguments(subparser)
        for arg in self.args:
            arg = arg.copy()
            subparser.add_argument(arg.pop("name"), **arg)

        subparser.set_defaults(func=self.handle)

    @property
    def client(self):
        """Get the client instance"""
        if "client" in self._cache:
            return self._cache["client"]
        client = rpyc.connect("localhost", 18861)
        self._cache["client"] = client
        return client

    def rpc(self, service, method, *args, **kwargs):
        """Call a remote method"""
        return self.client.root.call(service, method, *args, **kwargs)

    @abstractmethod
    def handle(self, args):
        """Run the command. Override this method in your subclass"""

    def setup_common_arguments(self, parser):
        """Set common arguments needed by all commands"""
        general_argument_group = parser.add_argument_group(title="Common arguments")

        general_argument_group.add_argument(
            "--config",
            dest="config_file",
            help="Config file to load, TOML (JSON or YAML not yet supported)",
            metavar="FILE",
        )

        general_argument_group.add_argument(
            "--log-level",
            help="Set the log level. Overrides any value set in config. "
            "One of debug, info, warning, critical, exception.",
            metavar="LOG_LEVEL",
        )
