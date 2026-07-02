# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Matrix command: run E2E tests on cloud infrastructure (ADR 052 D9).

Canonical name is `matrix` (multi-distro across cloud images); `cloud` stays
registered as a deprecated alias. Each matrix leg IS a `hop3-test run
--provider hetzner`, so `matrix` shares `run`'s lexicon exactly (ADR 052 D1):
positional app names, `--from`, `--branch`, repeatable `--with`, group-level
`-v`. The only matrix-specific dimension is the image sweep (`--images`).
"""

from __future__ import annotations

import sys

import click

from hop3_testing.cli.deprecation import warn_deprecated


def _normalize_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize app directory paths (strip trailing slashes)."""
    return tuple(p.rstrip("/") for p in paths)


@click.command("matrix")
# App selection mirrors `run`: positional names/paths, not a bespoke --apps.
@click.argument("app_names", nargs=-1)
@click.option(
    "--provider",
    type=click.Choice(["hetzner"]),
    default="hetzner",
    help="Cloud provider (default: hetzner)",
)
# The sweep dimension — the one thing `matrix` adds over `run`.
@click.option(
    "--image",
    default=None,
    help="Single OS image — a sweep-of-one (e.g. ubuntu-24.04)",
)
@click.option(
    "--images",
    default=None,
    help="Comma-separated images or 'all' (e.g. ubuntu-24.04,debian-13)",
)
@click.option("--list-images", is_flag=True, help="List available OS images")
# Deploy lexicon — identical to `run` (each leg shells out to `run`).
@click.option(
    "--from",
    "--deploy-from",
    "deploy_from",
    type=click.Choice(["local", "git", "pypi"]),
    default="local",
    help="Install source: local | git | pypi (same as `run`)",
)
@click.option("--branch", default="devel", help="Git branch (if --from git)")
# ADR 052 D7 back-compat: the old boolean source flag, folded into --from. Kept
# hidden + warned so documented callers (ADR 044 nightly, nix notes) still work.
@click.option(
    "--use-local-repo/--no-local-repo",
    "use_local_repo",
    default=None,
    hidden=True,
    help="Deprecated: use --from local | --from pypi",
)
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on the first failing image")
@click.option(
    "--with",
    "features",
    multiple=True,
    help=(
        "Extra features on top of the apps' auto-provisioned addons — "
        "repeatable or comma-separated (e.g. --with nix,redis, or --with all)"
    ),
)
@click.pass_context
def matrix_test(
    ctx: click.Context,
    app_names: tuple[str, ...],
    provider: str,
    image: str | None,
    images: str | None,
    list_images: bool,
    deploy_from: str,
    branch: str,
    use_local_repo: bool | None,
    fail_fast: bool,
    features: tuple[str, ...],
) -> None:
    """Run E2E tests across a matrix of cloud OS images (ADR 052 7b.7).

    Each image is a full `hop3-test run --provider hetzner`: provision a fresh
    box, deploy Hop3, run the apps, and persist to the shared result store (so
    cloud runs show up in the dashboard and `hop3-test why`). A lone --image is
    a sweep-of-one; test one distro with `hop3-test run --provider hetzner`.

    \b
    Examples:
      hop3-test matrix --images ubuntu-24.04,debian-13   # Several distros
      hop3-test matrix --images all                      # All distros
      hop3-test matrix --image ubuntu-24.04              # One distro
      hop3-test matrix --list-images                     # Available images
      hop3-test matrix apps/test-apps-procfile demos     # Specific dirs

    Requires HETZNER_API_TOKEN + HETZNER_SERVER_ID (a dedicated throwaway box).
    """
    # ADR 052 D9/D3: deprecated spellings (still work; notice guides migration).
    if ctx.info_name == "cloud":
        warn_deprecated("cloud", "matrix", kind="command")
    for tok in sys.argv[1:]:
        if tok == "--deploy-from" or tok.startswith("--deploy-from="):
            warn_deprecated("--deploy-from", "--from")
            break

    # ADR 052 D7: the old boolean source flag maps onto --from (canonical).
    if use_local_repo is not None:
        warn_deprecated("--use-local-repo/--no-local-repo", "--from")
        deploy_from = "local" if use_local_repo else "pypi"

    if list_images:
        _show_images(provider)
        return

    verbose = ctx.obj["verbose"]

    # Accept both --with nix --with redis and --with nix,redis (like `run`).
    features = tuple(
        part.strip() for feat in features for part in feat.split(",") if part.strip()
    )

    suites = _normalize_paths(app_names) or ("apps/test-apps-procfile",)

    # A lone --image is a sweep-of-one; default to the standard image otherwise.
    images_str = images or image or "ubuntu-24.04"
    _run_multi_distro(
        provider=provider,
        images_str=images_str,
        app_names=suites,
        source=deploy_from,
        branch=branch,
        fail_fast=fail_fast,
        verbose=verbose,
        features=features,
        ctx=ctx,
    )


def _show_images(provider: str) -> None:
    """Show available OS images for a provider."""
    from rich.console import Console  # noqa: PLC0415
    from rich.table import Table  # noqa: PLC0415

    from hop3_testing.system_tests.multi_distro import (  # noqa: PLC0415
        HETZNER_IMAGES,
    )

    # For now only Hetzner; when adding providers, dispatch here
    image_list = HETZNER_IMAGES

    console = Console()
    console.print(f"\n[bold]Available OS images ({provider})[/]\n")
    table = Table()
    table.add_column("Image Name", style="cyan")
    table.add_column("Description")
    table.add_column("Notes")
    for img_name, desc, notes in image_list:
        table.add_row(img_name, desc, notes)
    console.print(table)


def _run_multi_distro(
    *,
    provider: str,
    images_str: str,
    app_names: tuple[str, ...],
    source: str,
    branch: str,
    fail_fast: bool,
    verbose: bool,
    features: tuple[str, ...],
    ctx: click.Context,
) -> None:
    """Run tests across multiple distributions."""
    from hop3_testing.system_tests.multi_distro import (  # noqa: PLC0415
        HETZNER_IMAGES,
        run_multi_distro_tests,
    )

    # Resolve "all" to the full image list for this provider
    if images_str == "all":
        image_list = [img[0] for img in HETZNER_IMAGES]
    else:
        image_list = [img.strip() for img in images_str.split(",") if img.strip()]

    # --with adds EXTRA features (apps' declared addons are auto-provisioned by
    # `run`). Pass each through as its own --with, mirroring the `run` grammar.
    extra_args: list[str] = []
    for feat in features:
        extra_args += ["--with", feat]

    results = run_multi_distro_tests(
        images=image_list,
        app_names=app_names,
        source=source,
        branch=branch,
        stop_on_failure=fail_fast,
        verbose=verbose,
        extra_args=extra_args or None,
    )

    if any(not r.success for r in results):
        ctx.exit(1)
