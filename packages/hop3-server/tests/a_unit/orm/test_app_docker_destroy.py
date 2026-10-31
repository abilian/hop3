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

    def __init__(self, *, containers=(), images=(), networks=(), volumes=()) -> None:
        # Every resource held here carries the app's Compose project label.
        self.containers = set(containers)
        self.images = set(images)
        self.networks = set(networks)
        self.volumes = set(volumes)
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
        elif cmd[1:3] == ["network", "ls"] and cmd[-1].startswith("label="):
            out = "\n".join(sorted(self.networks))
        elif cmd[1:3] == ["network", "ls"]:
            wanted = cmd[-1].removeprefix("name=^").removesuffix("$")
            out = "net-id" if wanted in self.networks else ""
        elif cmd[1:3] == ["network", "rm"]:
            self.networks -= set(cmd[3:])
        elif cmd[1:3] == ["volume", "ls"]:
            out = "\n".join(sorted(self.volumes))
        elif cmd[1:3] == ["volume", "rm"]:
            self.volumes -= set(cmd[3:])
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


def test_destroy_removes_volumes_and_non_default_networks_down_left(
    monkeypatch, no_compose
):
    # `compose down --volumes` failing or timing out only logs; the safety
    # net must still remove the app's data volumes and every project network.
    app = _app()
    docker = FakeDocker(
        volumes={"bugsink-1780956657_data"},
        networks={"bugsink-1780956657_backend"},
    )
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.destroy_docker_compose(app)

    assert docker.volumes == set()
    assert docker.networks == set()
    filters = {c[-1] for c in docker.calls if c[1] == "volume" and c[2] == "ls"}
    assert filters == {"label=com.docker.compose.project=bugsink-1780956657"}


def test_destroy_names_a_surviving_volume(monkeypatch, no_compose):
    app = _app()
    docker = FakeDocker(volumes={"bugsink-1780956657_data"})

    def rm_without_effect(cmd, timeout):
        if cmd[1:3] == ["volume", "rm"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return docker(cmd, timeout)

    monkeypatch.setattr(docker_runtime, "run_docker", rm_without_effect)

    with pytest.raises(DockerError, match="survived") as raised:
        docker_runtime.destroy_docker_compose(app)
    assert "bugsink-1780956657_data" in str(raised.value)


def test_destroy_raises_when_volumes_cannot_be_listed(monkeypatch, no_compose):
    def volume_ls_hangs(cmd, timeout):
        if cmd[1:3] == ["volume", "ls"]:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return FakeDocker()(cmd, timeout)

    monkeypatch.setattr(docker_runtime, "run_docker", volume_ls_hangs)

    with pytest.raises(DockerError, match="docker volume ls"):
        docker_runtime.destroy_docker_compose(_app())


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
    monkeypatch.setattr(docker_runtime.shutil, "which", lambda name: None)
    docker = FakeDocker()
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.cleanup_orphan_docker_resources(App(name="native"))

    assert docker.calls == []


def test_orphan_cleanup_raises_when_docker_is_installed_but_failing(monkeypatch):
    monkeypatch.setattr(docker_runtime.shutil, "which", lambda name: "/bin/docker")
    docker = FakeDocker()
    docker.refuse = {"ps"}
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    with pytest.raises(DockerError, match="ps"):
        docker_runtime.cleanup_orphan_docker_resources(App(name="native"))


def test_orphan_cleanup_selects_by_project_label_not_name_substring(monkeypatch):
    # Docker's `name=` filter matches substrings: destroying `app` with it
    # force-removed `myapp-web-1`, another app's container.
    monkeypatch.setattr(docker_runtime.shutil, "which", lambda name: "/bin/docker")
    docker = FakeDocker()
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.cleanup_orphan_docker_resources(App(name="app"))

    filters = {c[c.index("--filter") + 1] for c in docker.calls if c[1] == "ps"}
    assert filters == {"label=com.docker.compose.project=app"}


def test_stop_reverifies_when_the_kill_fails(monkeypatch, no_compose):
    # A container that exits between the `ps` and the kill makes `docker kill`
    # fail; the re-check, not the kill's exit code, decides.
    app = _app()
    app.run_state = AppStateEnum.STOPPING
    docker = FakeDocker(containers={"c1"})

    def kill_fails_after_exit(cmd, timeout):
        if cmd[1] == "kill":
            docker.containers.clear()
            return SimpleNamespace(returncode=1, stdout="", stderr="not running")
        return docker(cmd, timeout)

    monkeypatch.setattr(docker_runtime, "run_docker", kill_fails_after_exit)

    docker_runtime.stop_docker_compose(app)

    assert app.run_state == AppStateEnum.STOPPED


def test_a_survivor_is_reported_with_what_the_kill_said(monkeypatch, no_compose):
    app = _app()
    app.run_state = AppStateEnum.STOPPING
    docker = FakeDocker(containers={"c1"})

    def kill_refused(cmd, timeout):
        if cmd[1] == "kill":
            return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
        return docker(cmd, timeout)

    monkeypatch.setattr(docker_runtime, "run_docker", kill_refused)

    with pytest.raises(RuntimeError, match="exited 1: permission denied"):
        docker_runtime.stop_docker_compose(app)


def test_force_cleanup_docker_image_targets_only_the_app_image(monkeypatch):
    app = App(name="myapp", runtime="docker-compose", image_tag="hop3/myapp:latest")
    docker = FakeDocker(images={"hop3/myapp:latest", "debian:bookworm-slim"})
    monkeypatch.setattr(docker_runtime, "run_docker", docker)

    docker_runtime.force_cleanup_docker_image(app)

    assert docker.images == {"debian:bookworm-slim"}
