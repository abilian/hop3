# Copyright (c) 2025, Abilian SAS
from __future__ import annotations


class Command:
    """Base class for CLI commands.

    Commands must have a `name` attribute and a `run()` method.
    Each command can define its own `run()` signature with typed parameters
    that match the arguments defined in `add_arguments()`.

    Example:
        @register
        class MyCmd(Command):
            name = "mycmd"

            def add_arguments(self, parser):
                parser.add_argument("file", type=str)

            def run(self, file: str) -> None:
                # file is properly typed
                print(f"Processing {file}")
    """

    name: str = ""
