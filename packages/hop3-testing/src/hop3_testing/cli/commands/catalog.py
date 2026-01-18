# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Catalog commands (list, show)."""

from __future__ import annotations

import json
import sys

import click

from hop3_testing.catalog import Catalog


@click.command("list")
@click.option(
    "--category", "-c", help="Filter by category (deployment, demo, tutorial)"
)
@click.option("--tier", "-t", help="Filter by tier (fast, medium, slow, very-slow)")
@click.option("--priority", "-p", help="Filter by priority (P0, P1, P2)")
@click.option("--tag", multiple=True, help="Filter by tag")
@click.option(
    "--format", "output_format", type=click.Choice(["table", "json"]), default="table"
)
@click.pass_context
def list_tests(
    ctx: click.Context,
    category: str | None,
    tier: str | None,
    priority: str | None,
    tag: tuple[str, ...],
    output_format: str,
) -> None:
    """List available tests."""
    catalog = Catalog(ctx.obj["root"])
    catalog.scan()

    tests = catalog.filter(
        categories=[category] if category else None,
        tiers=[tier] if tier else None,
        priorities=[priority] if priority else None,
        tags=list(tag) if tag else None,
    )

    if output_format == "json":
        output = [
            {
                "name": t.name,
                "category": t.category.value,
                "tier": t.tier.value,
                "priority": t.priority.value,
                "description": t.description,
            }
            for t in tests
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        # Table output
        click.echo(f"{'Name':<40} {'Category':<12} {'Tier':<10} {'Priority':<8}")
        click.echo("-" * 72)
        for t in tests:
            click.echo(
                f"{t.name:<40} {t.category.value:<12} {t.tier.value:<10} {t.priority.value:<8}"
            )
        click.echo(f"\nTotal: {len(tests)} tests")


@click.command("show")
@click.argument("test_name")
@click.pass_context
def show_test(ctx: click.Context, test_name: str) -> None:
    """Show details of a specific test."""
    catalog = Catalog(ctx.obj["root"])
    catalog.scan()

    test = catalog.get_test(test_name)
    if not test:
        click.echo(f"Test not found: {test_name}", err=True)
        sys.exit(1)

    assert test is not None  # Type narrowing after sys.exit
    click.echo(f"Name: {test.name}")
    click.echo(f"Category: {test.category.value}")
    click.echo(f"Tier: {test.tier.value}")
    click.echo(f"Priority: {test.priority.value}")
    if test.description:
        click.echo(f"Description: {test.description}")
    click.echo(f"Source: {test.source_path}")
    click.echo(f"Targets: {', '.join(t.value for t in test.requirements.targets)}")
    if test.requirements.services:
        click.echo(f"Services: {', '.join(test.requirements.services)}")
    if test.metadata.covers:
        click.echo(f"Tags: {', '.join(test.metadata.covers)}")
    click.echo(f"Validations: {len(test.validations)}")
