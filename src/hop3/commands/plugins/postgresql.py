# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import click
import pluggy

hookimpl = pluggy.HookimplMarker("hop3")


@hookimpl
def cli_commands():
    return pg


@click.group()
def pg() -> None:
    """PostgreSQL command plugin."""


@pg.command("pg:create")
@click.argument("name")
@click.argument("user")
@click.argument("password")
def pg_create(name, user, password) -> None:
    """PostgreSQL create a database."""


@pg.command("pg:drop")
@click.argument("name")
def pg_drop(name) -> None:
    """PostgreSQL drops a database."""


@pg.command("pg:import")
@click.argument("name")
def pg_import(name) -> None:
    """PostgreSQL import a database."""


@pg.command("pg:dump")
@click.argument("name")
def pg_dump(name) -> None:
    """PostgreSQL dumps a database SQL."""
