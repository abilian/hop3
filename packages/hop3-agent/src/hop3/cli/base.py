# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from argparse import ArgumentParser

COMMAND_REGISTRY = {}


class Cmd:
    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add arguments to the parser."""

    # NOTE: ignore while we figure out how to properly type this.
    # def run(self, /, **kwargs) -> None:
    #     """Run the command."""
    #     raise NotImplementedError


def command(cls):
    COMMAND_REGISTRY[cls.__name__] = cls
    return cls
