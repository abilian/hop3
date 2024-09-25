# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-3.0

from __future__ import annotations

import click
import pluggy

hookimpl = pluggy.HookimplMarker("hop3")


@hookimpl
def cli_commands():
    return redis


@click.group()
def redis() -> None:
    """Redis command plugin."""
