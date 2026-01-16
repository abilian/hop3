# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Build commands (build-ready-image, build-test-image)."""

from __future__ import annotations

import subprocess
import sys

import click


@click.command("build-ready-image")
@click.option("--tag", default="hop3-ready:latest", help="Image tag")
@click.option("--no-cache", is_flag=True, help="Build without Docker cache")
@click.pass_context
def build_ready_image(ctx: click.Context, tag: str, no_cache: bool) -> None:
    """Build the hop3-ready Docker image for app testing.

    This builds a Docker image with Hop3 pre-installed and ready to use.
    The image is used by 'hop3-test apps' for fast app testing.

    Examples:
        hop3-test build-ready-image                    # Build default image
        hop3-test build-ready-image --tag my-hop3:v1   # Custom tag
        hop3-test build-ready-image --no-cache         # Force rebuild
    """
    # Find project root and Dockerfile
    root = ctx.obj["root"]
    dockerfile_path = (
        root / "packages" / "hop3-server" / "tests" / "d_e2e" / "docker" / "Dockerfile"
    )

    if not dockerfile_path.exists():
        click.echo(f"Dockerfile not found at: {dockerfile_path}", err=True)
        sys.exit(1)

    click.echo(f"\n{'=' * 70}")
    click.echo("Building hop3-ready Docker image")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nDockerfile: {dockerfile_path}")
    click.echo(f"Context: {root}")
    click.echo(f"Tag: {tag}")
    click.echo()

    # Build command
    cmd = [
        "docker",
        "build",
        "-f",
        str(dockerfile_path),
        "-t",
        tag,
    ]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(root))

    click.echo(f"Running: {' '.join(cmd)}\n")

    try:
        subprocess.run(cmd, check=True)
        click.echo(f"\n{'=' * 70}")
        click.echo(f"Successfully built: {tag}")
        click.echo(f"{'=' * 70}")
        click.echo("\nYou can now run:")
        click.echo("  hop3-test apps           # Test all apps")
        click.echo("  hop3-test apps 010-flask # Test specific app")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nBuild failed with exit code {e.returncode}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Docker not found. Please install Docker.", err=True)
        sys.exit(1)


@click.command("build-test-image")
@click.option("--no-cache", is_flag=True, help="Build without Docker cache")
@click.pass_context
def build_test_image(ctx: click.Context, no_cache: bool) -> None:
    """Pre-build the Docker test image to warm the cache.

    The system tests automatically build a Docker image using docker build.
    Docker caches unchanged layers, so subsequent builds are fast.

    This command pre-builds the image so the first test run is also fast.
    It's optional - the image is built automatically when you run tests.

    Examples:
        hop3-test build-test-image              # Build with cache
        hop3-test build-test-image --no-cache   # Force full rebuild
    """
    # Find project root and Dockerfile
    root = ctx.obj["root"]
    dockerfile_path = (
        root / "packages" / "hop3-installer" / "docker" / "Dockerfile.base"
    )

    if not dockerfile_path.exists():
        click.echo(f"Dockerfile not found at: {dockerfile_path}", err=True)
        sys.exit(1)

    click.echo(f"\n{'=' * 70}")
    click.echo("Building hop3-test Docker image")
    click.echo("(Docker layer caching will make subsequent builds fast)")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nDockerfile: {dockerfile_path}")
    click.echo()

    # Build command
    cmd = [
        "docker",
        "build",
        "-f",
        str(dockerfile_path),
        "-t",
        "hop3-test:latest",
    ]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(root))

    try:
        subprocess.run(cmd, check=True)
        click.echo(f"\n{'=' * 70}")
        click.echo("Successfully built: hop3-test:latest")
        click.echo(f"{'=' * 70}")
        click.echo("\nDocker has cached the image layers.")
        click.echo("System tests will now start faster:")
        click.echo("  make test-system")
        click.echo("  hop3-test system")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nBuild failed with exit code {e.returncode}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Docker not found. Please install Docker.", err=True)
        sys.exit(1)
