from __future__ import annotations

import argparse
import dataclasses
from abc import ABCMeta, abstractmethod

__all__ = ['Command']

from typing import Any, Sequence, ClassVar


@dataclasses.dataclass(frozen=True)
class Command(metaclass=ABCMeta):
    # The command name
    name: ClassVar[str]

    # The command help
    help: ClassVar[str] = ""

    # Description of the command arguments
    args: ClassVar[Sequence[dict[str, Any]]] = ()

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

    @abstractmethod
    def handle(self, args):
        pass

    # @abstractmethod
    # def handle(self, args, config, plugin_registry: PluginRegistry, fake_it=False):
    #     pass
    #
    # def __init__(self, cli: CLI):
    #     self.cli = cli
    #
    # @abstractmethod
    # def run(self):
    #     pass
    #
    # def __call__(self, *args, **kwargs):
    #     return self.run(*args, **kwargs)
    #
    # @property
    # def name(self) -> str:
    #     return self.__class__.__name__.lower()
    #
    # @property
    # def help(self) -> str:
    #     return self.__doc__
    #
    # @property
    # def arguments(self) -> list:
    #     return []
    #
    # @property
    # def hide_from_help(self) -> bool:
    #     return False
    #
    # def __str__(self):
    #     return self.name
    #
    # def __repr__(self):
    #     return self.name
    #
    # def __eq__(self, other):
    #     return self.name == other.name
    #
    # def __hash__(self):
    #     return hash(self.name)

    def setup_common_arguments(self, parser):
        """Set common arguments needed by all commands"""
        general_argument_group = parser.add_argument_group(title="Common arguments")

        general_argument_group.add_argument(
            "--bus",
            "-b",
            dest="bus_module_name",
            metavar="BUS_MODULE",
            help=(
                "The bus module to import. Example 'bus', 'my_project.bus'. Defaults to "
                "the value of the LIGHTBUS_MODULE environment variable, or 'bus'"
            ),
        )

        general_argument_group.add_argument(
            "--service-name",
            "-s",
            help="Name of service in which this process resides. YOU SHOULD "
            "LIKELY SET THIS IN PRODUCTION. Can also be set using the "
            "LIGHTBUS_SERVICE_NAME environment. Will default to a random string.",
        )

        general_argument_group.add_argument(
            "--process-name",
            "-p",
            help="A unique name of this process within the service. Can also be set using the "
            "LIGHTBUS_PROCESS_NAME environment. Will default to a random string.",
        )

        general_argument_group.add_argument(
            "--config",
            dest="config_file",
            help="Config file to load, JSON or YAML",
            metavar="FILE",
        )

        general_argument_group.add_argument(
            "--log-level",
            help="Set the log level. Overrides any value set in config. "
            "One of debug, info, warning, critical, exception.",
            metavar="LOG_LEVEL",
        )
