# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from .rpc import setup as rpc_setup
from .terminal import setup as terminal_setup


def setup(context):
    rpc_setup(context)
    terminal_setup(context)
