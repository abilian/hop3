# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class App:
    name: str
    is_running: bool = False
