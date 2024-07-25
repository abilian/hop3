# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import argparse
import dataclasses
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Sequence

__all__ = ["Command"]

from hop3_cli.context import Context


@dataclasses.dataclass(frozen=True)
class Command(ABC):
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

    @abstractmethod
    def handle(self, args: argparse.Namespace, context: Context):
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
