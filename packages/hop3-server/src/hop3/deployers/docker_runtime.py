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
from typing import TYPE_CHECKING, NoReturn

from hop3.lib import Diagnosis, format_diagnosis, get_free_port, log
from hop3.orm.app import AppStateEnum

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm.app import App

__all__ = [
    "DockerError",
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
        _docker(app, "kill", *running, action="force-kill its containers")
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

    # Safety nets: 'down' is best-effort (check=False, may time out). Remove
    # any container it left behind — otherwise it keeps the published host
    # port and collides by name on the next deploy — then the network and the
    # per-app image `down --rmi` may have missed (e.g. the compose file was
    # already gone; base images are never tagged `hop3/...`). Every step runs,
    # and every failure is reported: destroy must never claim a clean teardown
    # over a leftover.
    failures: list[str] = []
    for step in (
        _remove_leftover_containers,
        force_cleanup_docker_network,
        force_cleanup_docker_image,
    ):
        try:
            step(app)
        except DockerError as e:
            failures.append(str(e))
    if failures:
        raise DockerError("\n\n".join(failures))


def _remove_leftover_containers(app: App) -> None:
    """Force-remove every container of the app's project, and verify it."""
    leftover = app_container_ids(app)
    if not leftover:
        return
    log(
        f"Force-removing {len(leftover)} leftover container(s) for "
        f"'{app.name}' after compose down",
        level=2,
        fg="yellow",
    )
    _docker(app, "rm", "-f", *leftover, action="remove its leftover containers")
    still = app_container_ids(app)
    if still:
        _fail(
            app,
            "remove its leftover containers",
            f"{len(still)} container(s) survived `docker rm -f`: {', '.join(still)}",
        )


def app_container_ids(app: App, *, running_only: bool = False) -> list[str]:
    """
    IDs of this app's containers, matched by Compose project label.

    ``running_only`` limits to currently-running containers; otherwise it
    includes stopped ones too. The project label is an exact match (unlike a
    container-name substring), so it can't catch a different app by prefix.
    Raises :class:`DockerError` when Docker can't answer: an empty list must
    mean "no containers", never "couldn't ask".
    """
    flag = "-q" if running_only else "-aq"
    result = _docker(
        app,
        "ps",
        flag,
        "--filter",
        f"label=com.docker.compose.project={app.name}",
        action="list its containers",
    )
    return result.stdout.split()


def force_cleanup_docker_image(app: App) -> None:
    """Force-remove the app's own image, and verify it is gone."""
    image_tag = app.image_tag or f"hop3/{app.name.lower()}:latest"
    action = f"remove its image {image_tag}"
    if not _docker(app, "images", "-q", image_tag, action=action).stdout.strip():
        return
    _docker(app, "rmi", "-f", image_tag, action=action)
    if _docker(app, "images", "-q", image_tag, action=action).stdout.strip():
        _fail(app, action, "the image is still present after `docker rmi -f`")


def force_cleanup_docker_network(app: App) -> None:
    """Remove the app's default Compose network if it exists, and verify it."""
    network_name = f"{app.name}_default"
    action = f"remove its network {network_name}"
    if not _network_exists(app, network_name, action):
        return
    _docker(app, "network", "rm", network_name, action=action)
    if _network_exists(app, network_name, action):
        _fail(app, action, "the network is still present after `docker network rm`")
    log(f"Removed orphan network '{network_name}'", level=2, fg="green")


def _network_exists(app: App, network_name: str, action: str) -> bool:
    listed = _docker(
        app, "network", "ls", "-q", "--filter", f"name=^{network_name}$", action=action
    )
    return bool(listed.stdout.strip())


class DockerError(RuntimeError):
    """A Docker operation on an app failed; the message is a formatted Diagnosis."""


def _fail(app: App, action: str, reason: str) -> NoReturn:
    raise DockerError(
        format_diagnosis(
            Diagnosis(
                component="Docker runtime",
                action=f"{action} for '{app.name}'",
                reason=reason,
                hint=(
                    "check that the Docker daemon is running (`docker info`), "
                    "then retry; until then the leftover holds the app's name, "
                    "ports or disk"
                ),
            )
        )
    )


def _docker(
    app: App, *args: str, action: str, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    """Run ``docker <args>``; raise :class:`DockerError` unless it succeeds."""
    cmd = ["docker", *args]
    shown = " ".join(cmd)
    try:
        result = run_docker(cmd, timeout)
    except FileNotFoundError:
        _fail(app, action, f"`{shown}` failed: the docker CLI is not installed")
    except subprocess.TimeoutExpired:
        _fail(app, action, f"`{shown}` did not answer within {timeout}s")
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip() or "no output"
        _fail(app, action, f"`{shown}` exited {result.returncode}: {output}")
    return result


def run_docker(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """The one place this module runs the docker CLI (the seam tests replace)."""
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, timeout=timeout
    )


def cleanup_orphan_docker_resources(app: App) -> None:
    """
    Remove orphan Docker containers/networks for this app, and verify it.

    Called when destroying an app that isn't marked docker-compose but may
    still own containers from an earlier deployment or a failed cleanup.

    A host without the docker CLI is a legitimate no-op — most apps aren't
    containerised. A Docker that is installed but does not answer is not: it
    may still hold a container with the app's ports and name, so the next
    deploy of that name would fail with an opaque error, and only after
    something else has run. That raises, as does a container that survives
    removal.
    """
    name_filter = f"name={app.name}-"
    action = "list its orphan containers"
    try:
        found = run_docker(["docker", "ps", "-aq", "--filter", name_filter], 30)
    except FileNotFoundError:
        return  # no Docker on this host: nothing of ours can exist under it
    except subprocess.TimeoutExpired:
        _fail(app, action, "`docker ps` did not answer within 30s")
    if found.returncode != 0:
        output = (found.stderr or found.stdout or "").strip() or "no output"
        _fail(app, action, f"`docker ps` exited {found.returncode}: {output}")

    container_ids = found.stdout.split()
    if container_ids:
        log(
            f"Found {len(container_ids)} orphan container(s) for '{app.name}'",
            level=2,
            fg="yellow",
        )
        _docker(app, "rm", "-f", *container_ids, action="remove its orphan containers")
    force_cleanup_docker_network(app)

    # Verify the effect, not the exit codes.
    leftover = _docker(app, "ps", "-aq", "--filter", name_filter, action=action)
    if leftover.stdout.split():
        ids = leftover.stdout.split()
        _fail(
            app,
            "remove its orphan containers",
            f"{len(ids)} container(s) survived `docker rm -f`: {', '.join(ids)}; "
            f"they still hold the app's name and ports",
        )


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
