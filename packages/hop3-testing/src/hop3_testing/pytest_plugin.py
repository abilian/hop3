# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Fixtures for any package whose e2e layer needs a Docker daemon and the e2e image.

Registered as a `pytest11` entry point, so the fixtures are available in every
package without a conftest importing another package's conftest — which is not a
thing pytest supports, and which `pytest_plugins` in a non-root conftest cannot
express either.

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
    credential-helper directives (``credsStore``/``credHelpers``) stripped, so
    building or pulling public images never shells out to a credential helper
    (e.g. ``docker-credential-osxkeychain``) — which pops an interactive keychain
    prompt and fails the run if declined (docker-py's ``build()`` eagerly
    resolves all credentials). The docker context (``currentContext``) and inline
    ``auths`` are preserved, so connectivity is unchanged.
    """
    import docker

    cfg_dir = tmp_path_factory.mktemp("docker-config")
    real_cfg = Path.home() / ".docker" / "config.json"
    data: dict[str, Any] = {}
    if real_cfg.exists():
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(real_cfg.read_text())
    data.pop("credsStore", None)
    data.pop("credHelpers", None)
    (cfg_dir / "config.json").write_text(json.dumps(data))

    prev = os.environ.get("DOCKER_CONFIG")
    os.environ["DOCKER_CONFIG"] = str(cfg_dir)
    try:
        client = docker.from_env()
        client.ping()  # connectivity check (context preserved)
        yield client
        client.close()
    finally:
        if prev is None:
            os.environ.pop("DOCKER_CONFIG", None)
        else:
            os.environ["DOCKER_CONFIG"] = prev


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """The e2e image, rebuilt when the source it bakes has changed.

    The staleness gate lives in `hop3_testing.e2e_image`; see its module docstring
    for why it is shared rather than copied per package.
    """
    from hop3_testing.e2e_image import ensure_e2e_image

    return ensure_e2e_image(docker_client)
