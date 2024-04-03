# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from hop3.util.console import log

__all__ = ["found_app"]


def found_app(kind) -> None:
    log(f"{kind} app detected.", level=5, fg="green")
