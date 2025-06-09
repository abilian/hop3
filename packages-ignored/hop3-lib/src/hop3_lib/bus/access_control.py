# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from typing import Any

from hop3_lib.bus.bus import CommandBus


# TODO: make a Protocol
class CommandAuthorizationChecker:
    def is_granted(self, command: Any) -> bool:
        return True  # Implement your access logic here


class SecureCommandBus(CommandBus):
    def __init__(self, authorization_checker: CommandAuthorizationChecker):
        super().__init__()
        self.authorization_checker = authorization_checker

    def dispatch(self, command: Any):
        if not self.authorization_checker.is_granted(command):
            raise PermissionError("Command not authorized")
        super().dispatch(command)
