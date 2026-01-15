# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Mode commands (dev, ci, nightly)."""

from __future__ import annotations

import click

from hop3_testing.cli.runners import run_tests


@click.command("dev")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--keep", is_flag=True, help="Keep target after tests")
@click.option("--keep-apps", is_flag=True, help="Keep apps deployed after testing")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def dev(
    ctx: click.Context,
    target: str,
    host: str | None,
    keep: bool,
    keep_apps: bool,
    fail_fast: bool,
) -> None:
    """Run developer tests (fast, P0 only).

    This runs fast P0 deployment tests in Docker. Use this for quick
    validation during development.
    """
    run_tests(
        ctx,
        mode="dev",
        target_type=target,
        host=host,
        keep_target=keep,
        keep_apps=keep_apps,
        fail_fast=fail_fast,
    )


@click.command("ci")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def ci(
    ctx: click.Context,
    target: str,
    host: str | None,
    fail_fast: bool,
) -> None:
    """Run CI tests (fast+medium, P0).

    This runs fast and medium P0 tests suitable for CI pipelines.
    """
    run_tests(
        ctx,
        mode="ci",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )


@click.command("nightly")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def nightly(
    ctx: click.Context,
    target: str,
    host: str | None,
    fail_fast: bool,
) -> None:
    """Run nightly tests (all tiers, all priorities).

    This runs all deployment tests, demos, and tutorials. Intended for
    nightly CI builds with more time.
    """
    run_tests(
        ctx,
        mode="nightly",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )
