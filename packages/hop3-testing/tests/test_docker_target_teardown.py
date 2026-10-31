# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A Docker target leaves no container behind, or says it did.

A start that failed after the deploy created its container left it on the
Docker host ("Created", the upgrade chain, 2026-10-30): the teardown only
removed a container once the start had succeeded. And a teardown whose
remove failed printed a warning, then "Container stopped.".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from docker.errors import APIError, NotFound
from hop3_testing.targets import (
    DeploymentConfig,
    DockerConfig,
    DockerTarget,
    docker as docker_module,
)
from hop3_testing.targets.helpers import (
    ContainerLeftBehindError,
    DockerContainerHelper,
)

_NAME = "hop3-teardown-test"


class _Container:
    def __init__(self, *, remove_error: Exception | None = None) -> None:
        self.name = _NAME
        self.removed = False
        self.status = "exited"
        self._remove_error = remove_error

    def reload(self) -> None: ...

    def remove(self, *, force: bool) -> None:
        assert force
        if self._remove_error:
            raise self._remove_error
        self.removed = True


class _Client:
    """The daemon: what exists before the deploy, and what the deploy creates."""

    def __init__(self, *, before: _Container | None, created: _Container | None):
        self._before, self._created = before, created
        self.deployed = False
        self.containers = SimpleNamespace(get=self._get)

    def _get(self, name: str) -> _Container:
        assert name == _NAME
        found = self._before or (self._created if self.deployed else None)
        if found is None:
            msg = "no such container"
            raise NotFound(msg)
        return found


def _failed_start(monkeypatch, client: _Client) -> DockerTarget:
    target = DockerTarget(
        DockerConfig(container_name=_NAME), deployment=DeploymentConfig(clean=True)
    )
    target._client = client

    def deploy(**_kwargs: object) -> tuple[bool, float]:
        client.deployed = True
        return False, 0.0

    monkeypatch.setattr(docker_module, "run_hop3_deploy", deploy)
    monkeypatch.setattr(target, "_save_diagnostics_on_error", lambda: None)
    return target


def test_a_failed_start_removes_the_container_its_deploy_created(monkeypatch):
    created = _Container()
    target = _failed_start(monkeypatch, _Client(before=None, created=created))

    with pytest.raises(RuntimeError, match="hop3-deploy failed"):
        target._deploy_and_start()
    assert created.removed


def test_a_failed_start_leaves_a_container_that_was_there_before(monkeypatch):
    before = _Container()
    target = _failed_start(monkeypatch, _Client(before=before, created=None))

    with pytest.raises(RuntimeError, match="hop3-deploy failed"):
        target._deploy_and_start()
    assert not before.removed


def test_a_failed_start_that_created_nothing_is_still_the_start_error(monkeypatch):
    target = _failed_start(monkeypatch, _Client(before=None, created=None))

    with pytest.raises(RuntimeError, match=r"^hop3-deploy failed$"):
        target._deploy_and_start()


def test_a_container_the_failed_start_cannot_remove_is_named(monkeypatch):
    stuck = _Container(remove_error=APIError("device busy"))
    target = _failed_start(monkeypatch, _Client(before=None, created=stuck))

    with pytest.raises(RuntimeError) as exc:
        target._deploy_and_start()
    message = str(exc.value)
    assert "hop3-deploy failed" in message  # why the start failed
    assert f"docker rm -f {_NAME}" in message


def test_a_teardown_that_cannot_remove_the_container_fails():
    target = DockerTarget(DockerConfig(container_name=_NAME))
    target._started = target._we_created_container = True
    target._container_helper = DockerContainerHelper(
        _Container(remove_error=APIError("device busy"))
    )

    with pytest.raises(RuntimeError, match=f"docker rm -f {_NAME}"):
        target.stop()


def test_a_failed_removal_still_deletes_the_ssh_key(tmp_path):
    helper = DockerContainerHelper(_Container(remove_error=APIError("device busy")))
    helper._ssh_key_path = tmp_path / "id_rsa"
    helper._ssh_key_path.write_text("key")

    with pytest.raises(ContainerLeftBehindError):
        helper.stop_and_remove()
    assert not helper._ssh_key_path.exists()


def test_a_container_already_gone_is_a_clean_teardown():
    helper = DockerContainerHelper(_Container(remove_error=NotFound("gone")))
    helper.stop_and_remove()
