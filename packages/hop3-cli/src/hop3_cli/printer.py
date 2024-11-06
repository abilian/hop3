# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

from dataclasses import dataclass

from tabulate import tabulate

Message = list[str]


@dataclass(frozen=True)
class Printer:
    verbose = False

    def print(self, msg) -> None:
        for item in msg:
            t = item["t"]
            meth = getattr(self, f"print_{t}")
            meth(item)

    def print_table(self, table: dict) -> None:
        headers = table["headers"]
        rows = table["rows"]
        print(tabulate(rows, headers=headers))

    def print_text(self, obj: dict) -> None:
        print(obj["text"])
