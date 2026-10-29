# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Docker teardown removes everything the app owned, and says so when it can't.

Without `--rmi all` (and the force-rmi safety net), every docker-variant
deploy leaks a 0.5-1.5 GB `hop3/<app>:latest` image — and since the app
name is timestamped, the tag is unique each run and never overwritten, so
the disk fills fast.

Docker that is missing, hung or failing used to read as "no containers"
(`app_container_ids` swallowed every error and returned []), so stop reported
STOPPED and destroy reported a clean teardown over live containers.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from hop3.deployers import docker_runtime
from hop3.deployers.docker_runtime import DockerError
from hop3.orm import App, AppStateEnum


class FakeDocker:
    """A docker CLI holding containers, images and networks as state."""

    def __init__(self, *, containers=(), images=(), networks=()) -> None:
        self.containers = set(containers)
        self.images = set(images)
        self.networks = set(networks)
        self.calls: list[list[str]] = []
        self.refuse: set[str] = set()  # subcommands that fail without effect

    def __call__(self, cmd: list[str], timeout: int):
        self.calls.append(cmd)
        sub = cmd[1]
        if sub in self.refuse:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"{sub}: denied")
        out = ""
        if sub == "ps":
            out = "\n".join(sorted(self.containers))
        elif sub in {"rm", "kill"}:
            self.containers -= set(cmd[3:] if sub == "rm" else cmd[2:])
        elif sub == "images":
            out = "img-id" if cmd[3] in self.images else ""
        elif sub == "rmi":
            self.images.discard(cmd[3])
        elif cmd[1:3] == ["network", "ls"]:
            wanted = cmd[-1].removeprefix("name=^").removesuffix("$")
            out = "net-id" if wanted in self.networks else ""
        elif cmd[1:3] == ["network", "rm"]:
            self.networks.discard(cmd[3])
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


def _app() -> App:
    return App(
        name="bugsink-1780956657",
        runtime="docker-compose",
        image_tag="hop3/bugsink-1780956657:latest",
    )


@pytest.fixture
def no_compose(monkeypatch):
    """`docker compose down` goes through subprocess.run directly; make it a no-op."""
    monkeypatch.setattr(
        docker_runtime.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )


def test_destroy_docker_compose_removes_image_network_and_containers(
    monkeypatch, no_compose
):
    app = _app()
    docker = FakeDocker(
        containers={"c1"},
        images={"hop3/bugsink-1780956657:latest"},
        networks={"bugsink-1780956657_default"},
    )
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.destroy_docker_compose(app)

    assert docker.containers == set()
    assert docker.images == set()
    assert docker.networks == set()


def test_destroy_down_requests_image_removal(monkeypatch):
    app = _app()
    downs: list[list[str]] = []
    monkeypatch.setattr(
        docker_runtime.subprocess,
        "run",
        lambda cmd, **k: (
            downs.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    monkeypatch.setattr(docker_runtime, "run_docker", FakeDocker())

    docker_runtime.destroy_docker_compose(app)

    down = next(c for c in downs if "down" in c)
    assert down[down.index("--rmi") + 1] == "all"


def test_destroy_reports_every_leftover_and_still_tries_each_step(
    monkeypatch, no_compose
):
    app = _app()
    docker = FakeDocker(
        containers={"c1"},
        images={"hop3/bugsink-1780956657:latest"},
        networks={"bugsink-1780956657_default"},
    )
    docker.refuse = {"rm", "rmi"}
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    with pytest.raises(DockerError) as raised:
        docker_runtime.destroy_docker_compose(app)

    message = str(raised.value)
    assert "rm: denied" in message
    assert "rmi: denied" in message
    # The network step ran despite the container failure before it.
    assert docker.networks == set()


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("docker"),
        subprocess.TimeoutExpired(["docker", "ps"], 30),
    ],
)
def test_container_listing_raises_when_docker_cannot_answer(monkeypatch, failure):
    def broken(cmd, timeout):
        raise failure

    monkeypatch.setattr(docker_runtime, "run_docker", broken)

    with pytest.raises(DockerError, match="list its containers"):
        docker_runtime.app_container_ids(_app())


def test_container_listing_raises_on_a_failing_daemon(monkeypatch):
    docker = FakeDocker()
    docker.refuse = {"ps"}
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    with pytest.raises(DockerError, match="ps: denied"):
        docker_runtime.app_container_ids(_app())


def test_stop_does_not_report_stopped_when_docker_cannot_answer(
    monkeypatch, no_compose
):
    app = _app()
    app.run_state = AppStateEnum.STOPPING
    docker = FakeDocker()
    docker.refuse = {"ps"}
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    with pytest.raises(DockerError):
        docker_runtime.stop_docker_compose(app)
    assert app.run_state != AppStateEnum.STOPPED


def test_orphan_cleanup_is_a_noop_without_a_docker_cli(monkeypatch):
    def missing(cmd, timeout):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(docker_runtime, "run_docker", missing)

    docker_runtime.cleanup_orphan_docker_resources(App(name="native"))


def test_orphan_cleanup_raises_when_docker_is_installed_but_failing(monkeypatch):
    docker = FakeDocker()
    docker.refuse = {"ps"}
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    with pytest.raises(DockerError, match="ps"):
        docker_runtime.cleanup_orphan_docker_resources(App(name="native"))


def test_force_cleanup_docker_image_targets_only_the_app_image(monkeypatch):
    app = App(name="myapp", runtime="docker-compose", image_tag="hop3/myapp:latest")
    docker = FakeDocker(images={"hop3/myapp:latest", "debian:bookworm-slim"})
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.force_cleanup_docker_image(app)

    assert docker.images == {"debian:bookworm-slim"}
