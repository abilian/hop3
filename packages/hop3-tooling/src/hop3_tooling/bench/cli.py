# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""``hop3-bench`` — run the paper's read-only benchmark probes against a target.

Examples::

    hop3-bench memory --ssh hop3-dev.abilian.com
    hop3-bench closures --ssh hop3-dev.abilian.com miniflux gitea forgejo vikunja
"""

from __future__ import annotations

import json

import click

from hop3_tooling.bench.probes import (
    BenchError,
    control_plane_memory,
    docker_image_size,
    nix_closure,
    union_closure,
)
from hop3_tooling.bench.runner import local_runner, ssh_runner

# nixos-24.11 — the Hop3 nix-gen generator pin (plugins/build/nix/gen/templates/base.py)
DEFAULT_NIXPKGS_REV = "50ab793786d9de88ee30ec4e4c24fb4236fc2674"


def _runner(ssh: str | None):
    return ssh_runner(ssh) if ssh else local_runner()


@click.group()
def main() -> None:
    """Read-only, fail-loud benchmark probes for a Hop3 target."""


@main.command()
@click.option(
    "--ssh", default=None, help="Measure a remote host over SSH (else local)."
)
def memory(ssh: str | None) -> None:
    """Control-plane resident memory (PSS + RSS) of the running hop3-server."""
    mem = control_plane_memory(_runner(ssh))
    click.echo(
        json.dumps({
            "pids": list(mem.pids),
            "pss_mb": mem.pss_mb,
            "rss_mb": mem.rss_mb,
        })
    )


@main.command()
@click.argument("apps", nargs=-1, required=True)
@click.option("--ssh", default=None, help="Build + measure on a remote host over SSH.")
@click.option(
    "--nixpkgs-rev", default=DEFAULT_NIXPKGS_REV, help="Pinned nixpkgs commit."
)
def closures(apps: tuple[str, ...], ssh: str | None, nixpkgs_rev: str) -> None:
    """Build each app from the pinned nixpkgs and report closure size + path count."""
    run = _runner(ssh)
    out_paths: list[str] = []
    rows = []
    for app in apps:
        ref = f"github:NixOS/nixpkgs/{nixpkgs_rev}#{app}"
        out = run(f"nix build --no-link --print-out-paths {ref}").strip().splitlines()
        if not out:
            msg = f"{app}: nix build produced no output path"
            raise BenchError(msg)
        store_path = out[-1]
        out_paths.append(store_path)
        info = nix_closure(run, store_path)
        rows.append({
            "app": app,
            "closure_mb": info.closure_mb,
            "paths": info.path_count,
        })
        click.echo(
            f"{app:16} closure={info.closure_mb:>8.1f} MB  paths={info.path_count}"
        )
    if len(out_paths) > 1:
        union = union_closure(run, out_paths)
        summed = sum(r["closure_mb"] for r in rows)
        saving = round(100 * (1 - union.closure_mb / summed), 1) if summed else 0.0
        click.echo(
            f"{'union (dedup)':16} closure={union.closure_mb:>8.1f} MB  "
            f"paths={union.path_count}  saving={saving}%"
        )


@main.command("docker-size")
@click.argument("images", nargs=-1, required=True)
@click.option("--ssh", default=None, help="Inspect on a remote host over SSH.")
def docker_size(images: tuple[str, ...], ssh: str | None) -> None:
    """Uncompressed size of each (already-pulled) Docker image."""
    run = _runner(ssh)
    for image in images:
        size = docker_image_size(run, image)
        click.echo(f"{image:40} {round(size / 1_000_000, 1):>8.1f} MB")


if __name__ == "__main__":
    main()
