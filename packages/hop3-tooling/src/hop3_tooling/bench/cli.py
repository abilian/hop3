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
from pathlib import Path

import click

from hop3_tooling.bench.probes import (
    BenchError,
    cgroup_memory,
    control_plane_memory,
    docker_image_size,
    nix_closure,
    nix_rebuild_reproducible,
    nix_update_delta,
    union_closure,
)
from hop3_tooling.bench.report import render_all
from hop3_tooling.bench.runner import local_runner, ssh_runner

# nixos-24.11 — the Hop3 nix-gen generator pin (plugins/build/nix/gen/templates/base.py)
DEFAULT_NIXPKGS_REV = "50ab793786d9de88ee30ec4e4c24fb4236fc2674"


def _runner(ssh: str | None):
    return ssh_runner(ssh) if ssh else local_runner()


def _build_app(run, app: str, nixpkgs_rev: str) -> str:
    """Build an app from the pinned nixpkgs and return its store path."""
    ref = f"github:NixOS/nixpkgs/{nixpkgs_rev}#{app}"
    out = run(f"nix build --no-link --print-out-paths {ref}").strip().splitlines()
    if not out:
        msg = f"{app}: nix build produced no output path"
        raise BenchError(msg)
    return out[-1]


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
        store_path = _build_app(run, app, nixpkgs_rev)
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


@main.command("update-delta")
@click.argument("apps", nargs=-1, required=True)
@click.option("--ssh", default=None, help="Build + measure on a remote host over SSH.")
@click.option(
    "--nixpkgs-rev", default=DEFAULT_NIXPKGS_REV, help="Pinned nixpkgs commit."
)
def update_delta(apps: tuple[str, ...], ssh: str | None, nixpkgs_rev: str) -> None:
    """Bytes re-sent on a source-only bump (the app's own store path)."""
    run = _runner(ssh)
    for app in apps:
        delta = nix_update_delta(run, _build_app(run, app, nixpkgs_rev))
        click.echo(
            f"{app:16} delta={delta.own_mb:>8.1f} MB"
            f"  ({delta.fraction_of_closure:.0%} of closure)"
        )


@main.command()
@click.argument("apps", nargs=-1, required=True)
@click.option("--ssh", default=None, help="Build + verify on a remote host over SSH.")
@click.option(
    "--nixpkgs-rev", default=DEFAULT_NIXPKGS_REV, help="Pinned nixpkgs commit."
)
def reproducibility(apps: tuple[str, ...], ssh: str | None, nixpkgs_rev: str) -> None:
    """Rebuild from source; report whether the output is byte-identical."""
    run = _runner(ssh)
    for app in apps:
        check = nix_rebuild_reproducible(run, _build_app(run, app, nixpkgs_rev))
        status = "reproducible" if check.reproducible else "NOT reproducible"
        click.echo(f"{app:16} {status:18} {check.nar_hash}")


@main.command("cgroup-memory")
@click.argument("services", nargs=-1, required=True)
@click.option("--ssh", default=None, help="Measure a remote host over SSH.")
def cgroup_mem(services: tuple[str, ...], ssh: str | None) -> None:
    """cgroup memory.current of systemd services — the cross-stack metric.

    Use the same metric for every stack, e.g. hop3-server/hop3-rootd on a Hop3
    box, ``docker`` on a Compose box, ``k3s`` on a K3s box.
    """
    run = _runner(ssh)
    for service in services:
        mb = round(cgroup_memory(run, service) / 1_000_000, 1)
        click.echo(f"{service:24} {mb:>8.1f} MB")


@main.command()
@click.option(
    "--results",
    type=click.Path(exists=True, path_type=Path),
    default="notes/benchmarks/2026-07-19-preliminary.json",
    show_default=True,
    help="Raw measurement run to render.",
)
def report(results: Path) -> None:
    """Regenerate the paper's tables from a raw run.

    Every figure quoted in the paper's evaluation comes from here, so no number
    is hand-transcribed and each traces to the run that produced it.
    """
    click.echo(render_all(json.loads(results.read_text())))


if __name__ == "__main__":
    main()
