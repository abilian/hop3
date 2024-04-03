from __future__ import annotations

import click
import pluggy

hookimpl = pluggy.HookimplMarker("hop3")


@hookimpl
def cli_commands():
    return pg


@click.group()
def pg() -> None:
    """PostgreSQL command plugin"""
    pass


@pg.command("pg:create")
@click.argument("name")
@click.argument("user")
@click.argument("password")
def pg_create(name, user, password) -> None:
    """PostgreSQL create a database"""
    pass


@pg.command("pg:drop")
@click.argument("name")
def pg_drop(name) -> None:
    """PostgreSQL drops a database"""
    pass


@pg.command("pg:import")
@click.argument("name")
def pg_import(name) -> None:
    """PostgreSQL import a database"""
    pass


@pg.command("pg:dump")
@click.argument("name")
def pg_dump(name) -> None:
    """PostgreSQL dumps a database SQL"""
    pass
