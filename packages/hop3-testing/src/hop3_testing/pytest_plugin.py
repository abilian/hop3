# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Fixtures for any package whose e2e layer needs a Docker daemon and the e2e image.

Registered as a `pytest11` entry point, so the fixtures are available in every
package without a conftest importing another package's conftest. Pytest does
not support such an import, and `pytest_plugins` in a non-root conftest cannot
express it either.

Everything here is lazy: the module imports nothing heavy at collection time, and a
session that never asks for `docker_client` never touches Docker. That matters
because this plugin loads for `make test-fast` too.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hop3_testing.targets.machine_lock import hold_docker_target

if TYPE_CHECKING:
    from collections.abc import Generator

    import docker


@pytest.fixture(scope="session")
def docker_client(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[docker.DockerClient]:
    """
    Provide a Docker client for tests.

    Point ``DOCKER_CONFIG`` at a copy of the user's config with the
    credential-helper directives (``credsStore``/``credHelpers``) stripped.
    Building or pulling public images then never shells out to a credential
    helper (e.g. ``docker-credential-osxkeychain``), which pops an interactive
    keychain prompt and fails the run if declined (docker-py's ``build()``
    eagerly resolves all credentials). Everything else is preserved: the inline
    ``auths``, and the docker context (``currentContext``) together with the
    ``contexts/`` directory it resolves through. The ``docker`` CLI a test
    shells out to (``hop3-deploy-server``, ``docker build``) thus reaches the
    daemon this fixture connects to. See ``write_docker_config``.

    The daemon is the one the ``docker`` CLI would use, pinned for the session
    (``pin_docker_endpoint``): a remote Docker host works like the local one.

    The session holds the machine's Docker-target lock, the one `hop3-test`
    takes: a second session would tear down the containers this one uses.
    """
    import docker
    from hop3_installer.deployer.docker_endpoint import pin_docker_endpoint

    cfg_dir = tmp_path_factory.mktemp("docker-config")
    write_docker_config(cfg_dir, Path.home() / ".docker")

    prev = os.environ.get("DOCKER_CONFIG")
    os.environ["DOCKER_CONFIG"] = str(cfg_dir)
    machine_lock = hold_docker_target()
    try:
        endpoint = pin_docker_endpoint()
        print(f"Docker daemon: {endpoint.url}")
        # paramiko for an ssh:// daemon, docker-py's default: over the `ssh`
        # binary (use_ssh_client) exec_run never returns.
        client = docker.from_env()
        client.ping()  # connectivity check
        yield client
        client.close()
    finally:
        machine_lock.close()
        if prev is None:
            os.environ.pop("DOCKER_CONFIG", None)
        else:
            os.environ["DOCKER_CONFIG"] = prev


def write_docker_config(cfg_dir: Path, real_dir: Path) -> None:
    """
    Populate ``cfg_dir`` as a ``DOCKER_CONFIG`` without credential helpers.

    ``config.json`` is copied minus ``credsStore``/``credHelpers``. The
    ``contexts/`` directory is symlinked into place because the CLI resolves
    ``currentContext`` through ``contexts/meta/<id>/meta.json`` (endpoint) and
    ``contexts/tls/``. A config that names a context it cannot find makes
    every ``docker`` invocation fail with "context not found", which the
    deployer reports as "Docker is not available" (OrbStack, Colima and Docker
    Desktop all run under a named context). docker-py ignores contexts, which is
    why the SDK-driven tests never noticed.
    """
    data: dict[str, Any] = {}
    real_cfg = real_dir / "config.json"
    if real_cfg.exists():
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(real_cfg.read_text())
    data.pop("credsStore", None)
    data.pop("credHelpers", None)
    (cfg_dir / "config.json").write_text(json.dumps(data))
    contexts = real_dir / "contexts"
    if contexts.is_dir():
        (cfg_dir / "contexts").symlink_to(contexts, target_is_directory=True)


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """The e2e image, rebuilt when the source it bakes has changed.

    The staleness gate lives in `hop3_testing.e2e_image`; see its module docstring
    for why it is shared rather than copied per package.
    """
    from hop3_testing.e2e_image import ensure_e2e_image

    return ensure_e2e_image(docker_client)
