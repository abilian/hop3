# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test command: deploy Hop3 and run tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import click

from hop3_testing.catalog import (
    CATALOG_STATUSES,
    Catalog,
    catalog_status_paths,
    default_scan_paths,
)
from hop3_testing.catalog.features import (
    merge_features,
    required_features_from_tests,
    validate_features,
)
from hop3_testing.catalog.loader import load_test_definition_smart
from hop3_testing.cli.deprecation import warn_deprecated
from hop3_testing.cli.runners import run_tests
from hop3_testing.selector import Selector, get_mode_config, list_modes
from hop3_testing.selector.modes import MODE_ALIASES
from hop3_testing.targets import DockerTarget, RemoteTarget
from hop3_testing.targets.config import DeploymentConfig, DockerConfig, RemoteConfig

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition


def _mode_choices() -> list[str]:
    """
    Valid ``--mode`` values: the current profiles plus back-compat aliases.

    Dynamic (not a hardcoded list) so renamed/added profiles — including custom
    ones from the Test Lab — are always accepted. The old hardcoded list is what
    silently rejected the renamed `smoke`/`curated`/`full` profiles.
    """
    return sorted(set(list_modes()) | set(MODE_ALIASES))


def _resolve_tests(
    app_names: tuple[str, ...],
    root: Path,
    mode: str,
    target_type: str,
    statuses: tuple[str, ...] = (),
    covers: tuple[str, ...] = (),
) -> list[TestDefinition]:
    """
    Resolve app_names into a list of TestDefinitions.

    Handles three cases:
    - Specific paths/names given -> look them up
    - Scan directories given -> scan and return all
    - Nothing given -> use mode-based selection on default paths

    ``statuses`` and ``covers`` are the two orthogonal axes of the catalog:
    maturity (the folder, ADR 059) and technology (the recipe's ``covers``
    tags). Keeping them separate is the point — pinning "the Nix suite" to a
    maturity folder held only while every Nix recipe happened to sit in one, and
    silently dropped the 34 that had moved on.
    """
    # A status *is* a directory, so it needs no branch of its own: it joins the
    # scan set and everything downstream treats it like any other path.
    if statuses:
        app_names += tuple(catalog_status_paths(root, statuses))

    return _by_covers(_resolve_named(app_names, root, mode, target_type), covers)


def _by_covers(
    tests: list[TestDefinition], covers: tuple[str, ...]
) -> list[TestDefinition]:
    """Keep the tests declaring any of the given ``[test].covers`` tags."""
    if not covers:
        return tests
    return [t for t in tests if any(c in t.metadata.covers for c in covers)]


def _resolve_named(
    app_names: tuple[str, ...],
    root: Path,
    mode: str,
    target_type: str,
) -> list[TestDefinition]:
    if not app_names:
        # No args: scan everything, use mode-based selection
        catalog = Catalog(root)
        catalog.scan(paths=default_scan_paths(root))
        mode_config = get_mode_config(mode)
        selector = Selector(catalog)
        return selector.select_for_target(mode_config, target_type)

    # Split args into scan directories vs specific apps
    scan_paths: list[str] = []
    direct_apps: list[str] = []
    for name in app_names:
        path = Path(name)
        if path.is_dir() and not (path / "hop3.toml").exists():
            scan_paths.append(name)
        else:
            direct_apps.append(name)

    tests: list[TestDefinition] = []
    catalog = Catalog(root)

    # Scan directories
    if scan_paths:
        catalog.scan(paths=scan_paths)
        tests.extend(catalog.filter())

    # Look up specific apps
    if direct_apps:
        if not scan_paths:
            # Need a catalog for name lookups
            parent_paths = list({str(Path(a).parent) for a in direct_apps if "/" in a})
            if parent_paths:
                catalog.scan(paths=parent_paths)

        for name in direct_apps:
            test, error = _lookup_test(name, catalog)
            if test:
                tests.append(test)
            elif error:
                click.echo(f"Warning: {error}", err=True)

    return tests


def _lookup_test(
    name: str, catalog: Catalog
) -> tuple[TestDefinition | None, str | None]:
    """Look up a test by name or path."""
    # Try path-based lookup
    if "/" in name or Path(name).is_dir():
        path = Path(name.rstrip("/"))
        test = catalog.get_test_by_path(path)
        if test:
            return test, None

        # Try loading directly from the directory
        if path.is_dir() and (
            (path / "hop3.toml").exists() or (path / "test.toml").exists()
        ):
            try:
                return load_test_definition_smart(path), None
            except Exception as e:
                return None, f"Failed to load {path}: {e}"

    # Try name-based lookup
    test = catalog.get_test(name)
    if test:
        return test, None

    # Try directory basename
    if "/" in name:
        test = catalog.get_test(Path(name).name)
        if test:
            return test, None

    return None, f"Test not found: {name}"


def _run_image_sweep(
    ctx: click.Context,
    *,
    images: str,
    app_names: tuple[str, ...],
    source: str,
    branch: str,
    fail_fast: bool,
    features: tuple[str, ...],
    verbose: bool,
) -> None:
    """
    Sweep a matrix of cloud OS images (ADR 052 D9, formerly the `matrix` cmd).

    Each image is a full `run --provider hetzner --image X` (provision → deploy →
    test → persist to the shared store), run serially and aggregated. Exits 1 if
    any image fails.
    """
    from hop3_testing.system_tests.multi_distro import (  # ruff:ignore[import-outside-top-level]
        HETZNER_IMAGES,
        run_multi_distro_tests,
    )

    if images == "all":
        image_list = [img[0] for img in HETZNER_IMAGES]
    else:
        image_list = [i.strip() for i in images.split(",") if i.strip()]

    # --with adds EXTRA features; the apps' declared addons are auto-provisioned
    # by each per-image `run`. Pass each as its own --with (the `run` grammar).
    extra_args: list[str] = []
    for feat in features:
        extra_args += ["--with", feat]

    results = run_multi_distro_tests(
        images=image_list,
        app_names=app_names or ("apps/test-apps-procfile",),
        source=source,
        branch=branch,
        stop_on_failure=fail_fast,
        verbose=verbose,
        extra_args=extra_args or None,
    )
    if any(not r.success for r in results):
        ctx.exit(1)


# `run` is the canonical name (ADR 052 D9): deploy to one target and run the
# catalog. `system` stays registered as an alias (see register_commands). The
# function keeps its historical name.
@click.command("run")
@click.argument("app_names", nargs=-1)
# Target type
@click.option(
    "--docker", "target_type", flag_value="docker", help="Test using a Docker container"
)
@click.option(
    "--ssh",
    "target_type",
    flag_value="remote",
    help="Deprecated: --host (or $HOP3_HOST) implies the remote target",
)
# Deployment. `--from` is the canonical spelling (ADR 052 D3); `--deploy-from`
# stays accepted (same dest) so existing callers keep working.
@click.option(
    "--from",
    "--deploy-from",
    "deploy_from",
    type=click.Choice(["local", "git", "pypi", "none"]),
    default="local",
    help="Install source: local | git | pypi | none (reuse existing)",
)
@click.option("--reuse", is_flag=True, help="Reuse existing deployment (skip deploy)")
@click.option("--branch", default="devel", help="Git branch (if --from git)")
@click.option("--clean", is_flag=True, help="Clean install (remove existing)")
# Connection
@click.option(
    "--host",
    envvar="HOP3_HOST",
    help="Remote server hostname/IP — selects the remote target (or $HOP3_HOST)",
)
@click.option("--port", type=int, default=22, help="SSH port")
@click.option("--user", default="root", help="SSH user")
# `--identity` is the canonical name (like `ssh -i`); `--ssh-key` stays as an
# accepted alias. HOP3_SSH_KEY is the canonical env; HOP3_TEST_SSH_KEY still works.
@click.option(
    "--identity",
    "--ssh-key",
    "ssh_key",
    envvar=["HOP3_SSH_KEY", "HOP3_TEST_SSH_KEY"],
    help="SSH private key path (like `ssh -i`; default: $HOP3_SSH_KEY)",
)
# Cloud provisioning (ADR 052 7b.7): --provider rebuilds a fresh server first,
# then deploys+tests it via the normal remote path.
@click.option(
    "--provider",
    type=click.Choice(["hetzner"]),
    default=None,
    help="Rebuild a fresh cloud server before deploying (e.g. hetzner)",
)
@click.option(
    "--server-id",
    type=int,
    default=None,
    help="Cloud server ID to rebuild for --provider (or HETZNER_SERVER_ID)",
)
@click.option(
    "--image",
    default=None,
    help="OS image for --provider (e.g. ubuntu-24.04)",
)
# --images sweeps a matrix of cloud OS images (ADR 052 D9): each image is a full
# `run --provider hetzner --image X`. Replaces the former `matrix`/`cloud` command.
@click.option(
    "--images",
    default=None,
    help="Sweep several cloud OS images: comma-separated or 'all' "
    "(e.g. ubuntu-24.04,debian-13). Implies --provider hetzner.",
)
@click.option("--list-images", is_flag=True, help="List available cloud OS images")
# Test options
@click.option(
    "--mode",
    type=click.Choice(_mode_choices()),
    default="smoke",
    help="Test profile (filters by tier/priority, or an explicit curated list)",
)
@click.option("--keep", is_flag=True, help="Keep target and apps after tests")
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode")
@click.option("--debug", is_flag=True, help="Show debug info on failure")
@click.option(
    "--narrate",
    is_flag=True,
    help="Print a per-test phase-timing breakdown (where the wall-clock went)",
)
@click.option("--logs-dir", type=click.Path(), help="Directory for per-app logs")
@click.option(
    "--with",
    "features",
    multiple=True,
    help="Extra features on top of the apps' auto-provisioned addons — repeatable or comma-separated (e.g. --with nix,redis, or --with all)",
)
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(CATALOG_STATUSES),
    help="Catalog maturity tier to run — repeatable (e.g. --status golden --status beta)",
)
@click.option(
    "--covers",
    multiple=True,
    help="Keep only apps declaring this [test].covers tag — repeatable (e.g. --covers nix)",
)
@click.pass_context
def system_test(  # ruff:ignore[complex-structure, too-many-branches, too-many-statements]
    ctx: click.Context,
    app_names: tuple[str, ...],
    target_type: str | None,
    deploy_from: str,
    reuse: bool,
    branch: str,
    clean: bool,
    host: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
    provider: str | None,
    server_id: int | None,
    image: str | None,
    images: str | None,
    list_images: bool,
    mode: str,
    keep: bool,
    fail_fast: bool,
    report: str,
    quiet: bool,
    debug: bool,
    narrate: bool,
    logs_dir: str | None,
    features: tuple[str, ...],
    statuses: tuple[str, ...],
    covers: tuple[str, ...],
) -> None:
    """
    Deploy Hop3 and run tests.

    Pass directories to scan or specific app paths/names.
    With --reuse, skips deployment (tests against existing server).

    \b
    Examples:
      hop3-test run --docker                  # Deploy + test defaults
      hop3-test run --docker apps/test-apps   # Scan a directory
      hop3-test run --docker --status golden  # One maturity tier
      hop3-test run --docker --covers nix      # Every Nix app, any tier
      hop3-test run --docker --clean --with all demos
      hop3-test run --host X                  # Remote (--host implies remote)
      hop3-test run --host X demos/demo03     # Specific app on a remote
      hop3-test run --reuse --host X          # Skip deploy
      hop3-test run --provider hetzner --image ubuntu-24.04       # One fresh cloud box
      hop3-test run --provider hetzner --images ubuntu-24.04,debian-13  # Sweep several
      hop3-test run --provider hetzner --images all               # Sweep every image
      hop3-test run --list-images                                 # Available cloud images
    """
    # ADR 052 D9/D2/D3 deprecated spellings (still work; notice guides migration).
    if ctx.info_name == "system":
        warn_deprecated("system", "run", kind="command")
    for old, new in (
        ("--deploy-from", "--from"),
        ("--ssh-key", "--identity"),
        ("--ssh", "--host"),
    ):
        if any(tok == old or tok.startswith(f"{old}=") for tok in sys.argv[1:]):
            warn_deprecated(old, new)

    verbose = ctx.obj["verbose"]

    # Accept both the repeatable form (--with nix --with redis) and the
    # comma-separated form (--with nix,redis), so one spelling works across
    # run / deploy-server / install-server (ADR 052 D1).
    features = tuple(
        part.strip() for feat in features for part in feat.split(",") if part.strip()
    )

    # ADR 052 D9: --list-images / --images fold the former `matrix`/`cloud`
    # command into `run`. --images sweeps a matrix of cloud OS images — each image
    # is a full `run --provider hetzner --image X` (provision → deploy → test →
    # persist), aggregated. Cardinality is a flag, not a separate command.
    if list_images:
        from hop3_testing.system_tests.multi_distro import (  # ruff:ignore[import-outside-top-level]
            show_images,
        )

        show_images(provider or "hetzner")
        return

    if images:
        if target_type == "docker":
            click.echo(
                "Error: --images sweeps cloud OS images; drop --docker.", err=True
            )
            sys.exit(1)
        _run_image_sweep(
            ctx,
            images=images,
            app_names=app_names,
            source=deploy_from if deploy_from != "none" else "local",
            branch=branch,
            fail_fast=fail_fast,
            features=features,
            verbose=verbose,
        )
        return

    # ADR 052 7b.7: --provider rebuilds a fresh cloud server, then falls through
    # to the normal remote deploy+test (which writes the shared result store, so
    # cloud runs show up in the dashboard and `why`).
    if provider:
        from hop3_testing.system_tests.provision import (  # ruff:ignore[import-outside-top-level]
            provision_server,
        )

        host = provision_server(
            provider=provider, server_id=server_id, image=image, verbose=verbose
        )
        target_type = "remote"

    # ADR 052 D2: --host (from the flag or $HOP3_HOST) implies the remote target
    # — no separate --ssh mode flag needed. --docker still selects Docker; --ssh
    # stays as a deprecated alias (warned above). The retired HOP3_TEST_HOST /
    # HOP3_DEV_HOST are NOT consulted (ADR 043): a target comes from --host or
    # $HOP3_HOST only, never from those legacy env vars.
    if target_type is None and host:
        target_type = "remote"

    if target_type is None:
        click.echo(
            "Error: specify --docker, or --host <server> for a remote target", err=True
        )
        click.echo("\nExamples:")
        click.echo("  hop3-test run --docker")
        click.echo("  hop3-test run --host server.com")
        sys.exit(1)

    if reuse:
        deploy_from = "none"

    # A remote target needs a host (from --host or $HOP3_HOST) — e.g. bare --ssh.
    if target_type == "remote" and not host:
        click.echo(
            "Error: remote target needs --host <server> (or $HOP3_HOST)", err=True
        )
        sys.exit(1)

    # Resolve tests
    root = ctx.obj["root"]
    tests = _resolve_tests(app_names, root, mode, target_type, statuses, covers)

    if not tests:
        # Exit non-zero: a selection that matches nothing is a mistake in the
        # selection, and reporting it as a clean run is how a typo'd --status or
        # a moved directory passes CI as "all green".
        click.echo("No tests found", err=True)
        if app_names:
            click.echo(f"Searched: {', '.join(app_names)}", err=True)
        if statuses:
            click.echo(f"Status: {', '.join(statuses)}", err=True)
        if covers:
            click.echo(f"Covers: {', '.join(covers)}", err=True)
        ctx.exit(1)

    # Show plan
    click.echo(f"\n{'=' * 70}")
    if deploy_from == "none":
        click.echo("Testing against existing Hop3 server")
    else:
        click.echo("Deploy Hop3 + run tests")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nTarget: {target_type}")
    if host:
        click.echo(f"Host: {host}")
    if deploy_from != "none":
        click.echo(f"Deploy from: {deploy_from}")
        if clean:
            click.echo("Clean install: True")
        if features:
            click.echo(f"Features: {', '.join(features)}")
    click.echo(f"\nTests to run ({len(tests)}):")
    for t in tests:
        click.echo(f"  - {t.name}")
    click.echo("")

    # Auto-provision the addons the selected apps DECLARE (hop3.toml [[addons]]),
    # so the server is installed with them. The framework installs what the apps
    # need — no manual --with, and no silently-skipped app.
    required_addons = required_features_from_tests(tests)

    # Build deployment config
    deployment: DeploymentConfig | None = None
    available_features = list(features) if features else None
    if deploy_from != "none":
        validate_features(required_addons)  # loud abort on an unprovisionable addon
        deploy_features = merge_features(features, required_addons)
        newly = [f for f in deploy_features if f not in features]
        if newly:
            click.echo(
                f"Auto-enabling addon feature(s) the apps require: {', '.join(newly)}"
            )
        deployment = DeploymentConfig(
            source=cast("Literal['local', 'git', 'pypi']", deploy_from),
            branch=branch,
            clean=clean,
            verbose=verbose,
            features=deploy_features,
        )
        # available_features must reflect what we PROVISIONED, or the service
        # filter would skip the very apps we just installed addons for.
        available_features = deploy_features

    # Create target
    target_obj: DockerTarget | RemoteTarget
    if target_type == "docker":
        docker_config = DockerConfig(
            container_name="hop3-system-test",
            reuse_container=deploy_from == "none",
        )
        target_obj = DockerTarget(docker_config, deployment=deployment)
    else:
        assert host is not None
        remote_config = RemoteConfig(
            host=host,
            port=port,
            user=user,
            ssh_key=ssh_key,
        )
        target_obj = RemoteTarget(remote_config, deployment=deployment)

    # Run tests
    start_msg = (
        "Connecting to existing server..."
        if deploy_from == "none"
        else "Deploying Hop3 via hop3-deploy..."
    )
    run_tests(
        ctx,
        tests,
        target_obj,
        keep=keep,
        fail_fast=fail_fast,
        report=report,
        quiet=quiet,
        debug=debug,
        narrate=narrate,
        logs_dir=logs_dir,
        start_message=start_msg,
        mode_label="system" if deploy_from != "none" else "reuse",
        selection_mode=mode,  # smoke/ci/broad/full -> the dashboard "scope"
        available_features=available_features,
    )
