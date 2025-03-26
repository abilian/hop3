# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from abc import ABC, abstractmethod


class Command(ABC):
    name: str = ""

    @abstractmethod
    def run(self):
        pass
