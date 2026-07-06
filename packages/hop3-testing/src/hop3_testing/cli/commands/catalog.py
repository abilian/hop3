# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""List command: discover and display available tests."""

from __future__ import annotations

import json
import sys

import click

from hop3_testing.catalog import Catalog, default_scan_paths


@click.command("list")
@click.argument("scan_paths", nargs=-1)
@click.option("--show", "show_name", help="Show details of a specific test")
@click.option("--tier", "-t", help="Filter by tier (fast, medium, slow, very-slow)")
@click.option("--priority", "-p", help="Filter by priority (P0, P1, P2)")
@click.option("--tag", multiple=True, help="Filter by tag")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
)
@click.pass_context
def list_tests(
    ctx: click.Context,
    scan_paths: tuple[str, ...],
    show_name: str | None,
    tier: str | None,
    priority: str | None,
    tag: tuple[str, ...],
    output_format: str,
) -> None:
    """List available tests.

    Pass directories to scan. If none given, scans apps/ and demos/.

    \b
    Examples:
      hop3-test list                           # All tests
      hop3-test list apps/real-apps-docker     # Only docker apps
      hop3-test list demos -t fast             # Fast demos
      hop3-test list --show 010-flask-pip-wsgi # Show details
    """
    root = ctx.obj["root"]
    catalog = Catalog(root)
    paths = list(scan_paths) if scan_paths else default_scan_paths(root)
    catalog.scan(paths=paths)

    # Show details for a specific test
    if show_name:
        test = catalog.get_test(show_name)
        if not test:
            click.echo(f"Test not found: {show_name}", err=True)
            sys.exit(1)

        assert test is not None
        click.echo(f"Name: {test.name}")
        click.echo(f"Type: {test.runner_type}")
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
        return

    # List tests
    tests = catalog.filter(
        tiers=[tier] if tier else None,
        priorities=[priority] if priority else None,
        tags=list(tag) if tag else None,
    )

    if output_format == "json":
        output = [
            {
                "name": t.name,
                "type": t.runner_type,
                "tier": t.tier.value,
                "priority": t.priority.value,
                "description": t.description,
            }
            for t in tests
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"{'Name':<40} {'Type':<12} {'Tier':<10} {'Priority':<8}")
        click.echo("-" * 72)
        for t in tests:
            click.echo(
                f"{t.name:<40} {t.runner_type:<12}"
                f" {t.tier.value:<10} {t.priority.value:<8}"
            )
        click.echo(f"\nTotal: {len(tests)} tests")
