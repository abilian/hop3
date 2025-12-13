# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base printer class for CLI output."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from tabulate import tabulate

Message = list[str]


@dataclass(frozen=True)
class Printer:
    """Basic printer for CLI output."""

    verbose: bool = False

    def print(self, msg) -> None:
        """Print a message using the appropriate method for each item type."""
        for item in msg:
            t = item["t"]
            meth = getattr(self, f"print_{t}")
            meth(item)

    def print_table(self, table: dict) -> None:
        """Print a table using tabulate."""
        headers = table["headers"]
        rows = table["rows"]
        print(tabulate(rows, headers=headers))

    def print_text(self, obj: dict) -> None:
        """Print plain text."""
        print(obj["text"])

    def print_error(self, obj: dict) -> None:
        """Print error messages to stderr."""
        print(f"ERROR: {obj['text']}", file=sys.stderr)

    def print_success(self, obj: dict) -> None:
        """Print success messages."""
        print(obj["text"])
