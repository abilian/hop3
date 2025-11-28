# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os

import granian
from granian.constants import Interfaces
from granian.log import LogLevels

# from hop3.config import MODE
from hop3.lib.registry import register

from ._base import Command

MODE = os.environ.get("HOP3_MODE", "production")
HOST = os.environ.get("HOP3_HOST", "0.0.0.0")

if MODE == "development":
    DEBUG = True
    LOG_LEVEL = LogLevels.debug
else:
    DEBUG = False
    LOG_LEVEL = LogLevels.info


@register
class Serve(Command):
    """Launch the server."""

    name = "serve"

    def run(self):
        reload = DEBUG
        granian.Granian(
            target="hop3.server.asgi:create_app",
            factory=True,
            address=HOST,
            # port=port,
            interface=Interfaces.ASGI,
            log_dictconfig={"root": {"level": "DEBUG"}} if not DEBUG else {},
            log_level=LOG_LEVEL,
            log_access=True,
            # loop=Loops.uvloop,
            reload=reload,
        ).serve()
