# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Docker Compose runtime operations for an app.

These used to be nine private methods on the :class:`~hop3.orm.app.App` SQLAlchemy
model — 477 lines of ``subprocess.run`` inside a persistence class, which is
where the teardown bugs lived and where nobody looked for them. The model owns
the app's state; running and tearing down containers is work done *to* an app,
so it lives out here with the rest of the imperative shell.

Every function takes the app as its first argument and drives the model's
state machine through ``App.transition_state``.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING

from hop3.lib import get_free_port, log
from hop3.orm.app import AppStateEnum

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm.app import App

__all__ = [
    "app_container_ids",
    "cleanup_orphan_docker_resources",
    "destroy_docker_compose",
    "find_compose_file",
    "force_cleanup_docker_image",
    "force_cleanup_docker_network",
    "get_docker_logs",
    "restart_docker_compose",
    "start_docker_compose",
    "stop_docker_compose",
]


def start_docker_compose(app: App) -> None:
    """Start the app using Docker Compose."""
    log(f"Starting Docker Compose app '{app.name}'...", level=2, fg="blue")

    # Use existing port or allocate a new one
    if not app.port or app.port == 0:
        app.port = get_free_port()
        log(f"Allocated port {app.port} for app", level=2)

    # Set up environment with allocated port and image tag
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PORT": str(app.port),
        "HOP3_IMAGE_TAG": app.image_tag or f"hop3/{app.name.lower()}:latest",
        "HOP3_APP_NAME": app.name,
        "HOP3_APP_PORT": str(app.port),
    }

    # Find the compose file (user-supplied or generated)
    compose_file = find_compose_file(app)
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "-p",
        app.name,
        "up",
        "-d",
        "--remove-orphans",
    ]

    try:
        subprocess.run(
            cmd,
            cwd=app.src_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        # Transition directly to RUNNING since docker compose up is synchronous
        app.transition_state(AppStateEnum.RUNNING)
        log(f"Docker Compose app '{app.name}' started.", level=2, fg="green")
    except subprocess.CalledProcessError as e:
        log(f"Docker Compose start failed: {e.stderr}", level=2, fg="red")
        raise
    except subprocess.TimeoutExpired:
        log("Docker Compose start timed out", level=2, fg="red")
        raise


def stop_docker_compose(app: App) -> None:
    """Stop Docker Compose app."""
    log(f"Stopping Docker Compose app '{app.name}'...", level=2, fg="blue")

    # Transition to STOPPING if coming from RUNNING
    if app.run_state == AppStateEnum.RUNNING:
        app.transition_state(AppStateEnum.STOPPING)

    # Find the compose file
    compose_file = find_compose_file(app)

    # Build environment with image tag for compose file substitution
    # This fixes the "HOP3_IMAGE_TAG not set" issue during stop
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PORT": str(app.port) if app.port else "8080",
        "HOP3_IMAGE_TAG": app.image_tag or f"hop3/{app.name.lower()}:latest",
        "HOP3_APP_NAME": app.name,
    }

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "-p", app.name, "stop"],
            cwd=app.src_path,
            env=env,
            check=False,  # Don't fail if already stopped
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            log(
                f"Docker Compose stop warning: {result.stderr}",
                level=2,
                fg="yellow",
            )
    except subprocess.TimeoutExpired:
        log(
            "Docker Compose stop timed out; verifying/force-killing",
            level=2,
            fg="yellow",
        )
    except Exception as e:
        log(
            f"Error stopping Docker Compose app: {e}; verifying",
            level=2,
            fg="yellow",
        )

    # Verify the containers are actually down; force-kill any survivor so its
    # published port is released, then confirm before reporting STOPPED — a
    # slow/failed 'compose stop' must NOT be reported as a clean STOPPED.
    running = app_container_ids(app, running_only=True)
    if running:
        log(
            f"Force-killing {len(running)} container(s) still running for '{app.name}'",
            level=2,
            fg="yellow",
        )
        with suppress(Exception):
            subprocess.run(
                ["docker", "kill", *running],
                capture_output=True,
                check=False,
                timeout=30,
            )
        running = app_container_ids(app, running_only=True)
    if running:
        msg = (
            f"Docker app '{app.name}' has {len(running)} container(s) still "
            f"running after stop+kill; they still hold their ports."
        )
        raise RuntimeError(msg)
    app.mark_stopped()
    log(f"Docker Compose app '{app.name}' stopped.", level=2, fg="green")


def destroy_docker_compose(app: App) -> None:
    """Destroy Docker Compose app - remove containers, networks, and volumes."""
    log(f"Destroying Docker Compose app '{app.name}'...", level=2, fg="yellow")

    # Build the docker compose command
    # Include -f to specify compose file if it exists, otherwise Docker Compose
    # won't know which networks/volumes to clean up
    compose_file = app.src_path / ".hop3-compose.yml"
    cmd = ["docker", "compose"]

    if compose_file.exists():
        cmd.extend(["-f", str(compose_file)])

    # `--rmi all` removes the per-app image (hop3/<app>:latest) too.
    # Without it, every deploy leaks a 0.5-1.5 GB image (the app name is
    # timestamped, so the tag is unique each run and never overwritten),
    # filling the disk fast. Base images are FROM layers, not compose
    # `image:` services, so they are NOT removed by this.
    cmd.extend([
        "-p",
        app.name,
        "down",
        "--rmi",
        "all",
        "--volumes",
        "--remove-orphans",
    ])

    # Build environment with image tag for compose file substitution
    # This fixes the "HOP3_IMAGE_TAG not set" issue during destroy
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PORT": str(app.port) if app.port else "8080",
        "HOP3_IMAGE_TAG": app.image_tag or f"hop3/{app.name.lower()}:latest",
        "HOP3_APP_NAME": app.name,
    }

    try:
        # Use 'down --volumes --remove-orphans' to fully clean up
        result = subprocess.run(
            cmd,
            cwd=app.src_path if app.src_path.exists() else None,
            env=env,
            check=False,  # Don't fail if containers don't exist
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log(f"Docker Compose app '{app.name}' destroyed.", level=2, fg="green")
        else:
            log(
                f"Docker Compose down returned {result.returncode}: {result.stderr}",
                level=2,
                fg="yellow",
            )
    except subprocess.TimeoutExpired:
        log("Docker Compose destroy timed out", level=2, fg="yellow")
    except Exception as e:
        log(f"Error destroying Docker Compose app: {e}", level=2, fg="yellow")

    # Safety net: 'down' is best-effort (check=False, may time out). Remove
    # any container it left behind — otherwise it keeps the published host
    # port and collides by name on the next deploy. (The orphan reaper is
    # only on the non-docker branch of destroy(), so do it here too.)
    leftover = app_container_ids(app)
    if leftover:
        log(
            f"Force-removing {len(leftover)} leftover container(s) for "
            f"'{app.name}' after compose down",
            level=2,
            fg="yellow",
        )
        with suppress(Exception):
            subprocess.run(
                ["docker", "rm", "-f", *leftover],
                capture_output=True,
                check=False,
                timeout=60,
            )

    # Always try to force cleanup the network as a safety measure
    # docker compose down should remove it, but sometimes networks are left behind
    force_cleanup_docker_network(app)

    # Safety net: remove the per-app image directly, in case `down --rmi`
    # missed it (e.g. the compose file was already gone). Base images are
    # never tagged `hop3/...`, so this only drops the app's own image.
    force_cleanup_docker_image(app)


def app_container_ids(app: App, *, running_only: bool = False) -> list[str]:
    """
    IDs of this app's containers, matched by Compose project label.

    ``running_only`` limits to currently-running containers; otherwise it
    includes stopped ones too. The project label is an exact match (unlike a
    container-name substring), so it can't catch a different app by prefix.
    """
    flag = "-q" if running_only else "-aq"
    with suppress(Exception):  # docker missing / timeout -> nothing to report
        result = subprocess.run(
            [
                "docker",
                "ps",
                flag,
                "--filter",
                f"label=com.docker.compose.project={app.name}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    return []


def force_cleanup_docker_image(app: App) -> None:
    """Force-remove the app's own image; safe no-op if already gone."""
    image_tag = app.image_tag or f"hop3/{app.name.lower()}:latest"
    with suppress(Exception):  # best-effort cleanup
        subprocess.run(
            ["docker", "rmi", "-f", image_tag],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def force_cleanup_docker_network(app: App) -> None:
    """Force cleanup of Docker network when compose file is missing."""
    network_name = f"{app.name}_default"
    log(
        f"Attempting to force remove network '{network_name}'...",
        level=2,
        fg="yellow",
    )
    try:
        result = subprocess.run(
            ["docker", "network", "rm", network_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            log(f"Removed orphan network '{network_name}'", level=2, fg="green")
        # Don't log error if network doesn't exist - that's fine
    except Exception:
        pass  # Best effort cleanup


def cleanup_orphan_docker_resources(app: App) -> None:
    """
    Remove orphan Docker containers/networks for this app, and verify it.

    Called when destroying an app that isn't marked docker-compose but may
    still own containers from an earlier deployment or a failed cleanup.

    Docker being absent is a legitimate no-op — most apps aren't
    containerised — but a container that *survives* removal is not. It
    holds the app's ports and name, so the next deploy of that name fails
    with an opaque error, and only after something else has run: the
    order-dependent heisenbug the platform rules single out. This used to
    swallow both the removal failure and the exception, so destroy
    reported success over a live container. It now re-checks and says so.
    """
    try:
        found = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"name={app.name}-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # No Docker on this host (or it didn't answer): nothing of ours can
        # be running under it, so there is nothing to clean up.
        return

    if found.returncode != 0 or not found.stdout.strip():
        force_cleanup_docker_network(app)
        return

    container_ids = found.stdout.strip().split("\n")
    log(
        f"Found {len(container_ids)} orphan container(s) for '{app.name}'",
        level=2,
        fg="yellow",
    )
    for container_id in container_ids:
        removed = subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if removed.returncode != 0:
            log(
                f"  docker rm -f {container_id} failed: {removed.stderr.strip()}",
                level=1,
                fg="yellow",
            )

    force_cleanup_docker_network(app)

    # Verify the effect, not the exit codes: re-query and fail loudly if
    # anything is still there, naming what and how to clear it.
    still = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name={app.name}-"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    leftover = still.stdout.strip().split("\n") if still.stdout.strip() else []
    if leftover:
        msg = (
            f"Teardown of '{app.name}' left {len(leftover)} Docker "
            f"container(s) running: {', '.join(leftover)}. They still hold "
            f"the app's name and ports, so the next deploy of '{app.name}' "
            f"will fail. Remove them with "
            f"`docker rm -f {' '.join(leftover)}` and retry the destroy."
        )
        raise RuntimeError(msg)


def restart_docker_compose(app: App) -> None:
    """Restart Docker Compose app."""
    log(f"Restarting Docker Compose app '{app.name}'...", level=2, fg="blue")

    # Build environment with image tag for compose file substitution
    # This fixes the "HOP3_IMAGE_TAG not set" issue during restart
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PORT": str(app.port) if app.port else "8080",
        "HOP3_IMAGE_TAG": app.image_tag or f"hop3/{app.name.lower()}:latest",
        "HOP3_APP_NAME": app.name,
        "HOP3_APP_PORT": str(app.port) if app.port else "8080",
    }

    try:
        subprocess.run(
            ["docker", "compose", "-p", app.name, "restart"],
            cwd=app.src_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        log(f"Docker Compose app '{app.name}' restarted.", level=2, fg="green")
    except subprocess.CalledProcessError as e:
        log(f"Docker Compose restart failed: {e.stderr}", level=2, fg="yellow")
        # Fall back to stop/start
        log("Falling back to stop/start...", level=2, fg="yellow")
        app.stop()
        app.start()
    except subprocess.TimeoutExpired:
        log(
            "Docker Compose restart timed out, trying stop/start...",
            level=2,
            fg="yellow",
        )
        app.stop()
        app.start()


def get_docker_logs(app: App, lines: int = 100, since: str | None = None) -> list[str]:
    """
    Get logs from Docker container(s) for this app.

    Args:
        lines: Number of log lines to retrieve
        since: Only return logs after this timestamp (ISO format)

    Returns:
        List of log lines
    """
    all_logs = []

    # Build environment with image tag for compose file substitution
    # This prevents "HOP3_IMAGE_TAG not set" warnings when parsing compose file
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PORT": str(app.port) if app.port else "8080",
        "HOP3_IMAGE_TAG": app.image_tag or f"hop3/{app.name.lower()}:latest",
        "HOP3_APP_NAME": app.name,
    }

    try:
        # Use docker compose logs to get logs from all containers
        compose_file = app.src_path / ".hop3-compose.yml"
        if compose_file.exists():
            cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                app.name,
                "logs",
                "--tail",
                str(lines),
                "--no-color",
            ]
            # Add --since filter if specified
            if since:
                cmd.extend(["--since", since])
        else:
            # Fall back to docker logs for the main container
            cmd = [
                "docker",
                "logs",
                "--tail",
                str(lines),
                f"{app.name}-web-1",
            ]
            # Add --since filter if specified (docker logs also supports it)
            if since:
                cmd.insert(-1, "--since")
                cmd.insert(-1, since)

        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.stdout:
            all_logs.append(f"==> docker logs ({app.name}) <==")
            all_logs.extend(result.stdout.strip().split("\n"))

        if result.stderr:
            # Docker compose logs often output to stderr
            if not result.stdout:
                all_logs.append(f"==> docker logs ({app.name}) <==")
            all_logs.extend(result.stderr.strip().split("\n"))

        if not all_logs:
            all_logs.append(f"No Docker logs found for app '{app.name}'")

    except subprocess.TimeoutExpired:
        all_logs.append(f"Timeout getting Docker logs for app '{app.name}'")
    except FileNotFoundError:
        all_logs.append("Docker command not found. Is Docker installed?")
    except Exception as e:
        all_logs.append(f"Error getting Docker logs: {e}")

    return all_logs


def find_compose_file(app: App) -> Path:
    """
    Find the compose file for this app.

    Returns the path to either:
    1. User-supplied compose file (docker-compose.yml, compose.yml, etc.)
    2. Hop3-generated compose file (.hop3-compose.yml)
    """
    # Check for user-supplied compose files first
    for filename in [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]:
        compose_path = app.src_path / filename
        if compose_path.exists():
            return compose_path

    # Fall back to Hop3-generated compose file
    generated_path = app.src_path / ".hop3-compose.yml"
    if generated_path.exists():
        return generated_path

    # If no compose file exists, return the generated path anyway
    # (docker compose will fail with a clear error message)
    return generated_path
