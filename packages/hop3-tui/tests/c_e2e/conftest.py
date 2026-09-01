# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A real hop3-server in Docker, a real app deployed on it, and a client pointed at both.

The rest of the suite proves the TUI against stubs and against the server's *source*.
Neither can prove what actually broke: that the argv the client builds is a command
the running server answers, and that what comes back parses. Both were wrong for a
long time while every test passed.

`docker_client` and `hop3_image` come from `hop3_testing`'s pytest plugin — the same
image, with the same staleness gate, that hop3-server's own e2e layer uses. The
container and the deploy are `DockerTarget` and `DeploymentSession`, which are
hop3-testing's deploy-and-verify primitives and what `hop3-test` drives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import DeploymentSession
from hop3_testing.targets.config import DockerConfig
from hop3_testing.targets.constants import create_test_token
from hop3_testing.targets.docker import DockerTarget
from hop3_tui.api.client import Hop3Client

if TYPE_CHECKING:
    from collections.abc import Generator

    from hop3_testing.targets.base import TargetInfo

#: Its own container name, so a TUI run and a server run can coexist.
CONTAINER = "hop3-tui-e2e"

#: The smallest thing the platform will accept. `requirements.txt` is the marker the
#: local builder needs to recognise the app at all, and it is empty so the deploy
#: installs nothing and takes seconds — the point is a real App row, not an
#: interesting application.
SAMPLE_APP = "tui-e2e-sample"
SAMPLE_PROCFILE = "web: python3 -m http.server $PORT\n"


@pytest.fixture(scope="session")
def hop3_target(hop3_image: str) -> Generator[DockerTarget]:
    """A running hop3-server, from the prebuilt e2e image."""
    target = DockerTarget(DockerConfig(image=hop3_image, container_name=CONTAINER))
    target.start()
    try:
        yield target
    finally:
        target.stop()


@pytest.fixture(scope="session")
def hop3_server(hop3_target: DockerTarget) -> TargetInfo:
    info = hop3_target.info  # raises if start() failed
    if not info.api_url:
        # Never hand out a half-started target: the tests would fail as "connection
        # refused" and read as a client bug rather than a harness one.
        msg = f"container {CONTAINER} started but mapped no API port"
        raise AssertionError(msg)
    return info


@pytest.fixture(scope="session")
def deployed_app(hop3_target: DockerTarget, tmp_path_factory) -> str:
    """One real application on the server, so the list commands return real tables.

    Without it every read runs against an empty server, which answers `{"t": "text"}`
    rather than a table — so no row is ever parsed and every response-shape assertion
    is vacuous. That is not hypothetical: it is exactly why this layer failed to catch
    the instance-count-read-as-a-port bug the first time it was run against it.
    """
    source_dir = tmp_path_factory.mktemp("sample-app")
    (source_dir / "Procfile").write_text(SAMPLE_PROCFILE)
    (source_dir / "requirements.txt").write_text("")
    (source_dir / "README.md").write_text("# tui e2e sample\n")

    session = DeploymentSession(
        AppSource(name=SAMPLE_APP, path=source_dir), hop3_target, app_name=SAMPLE_APP
    )
    session.prepare()
    session.deploy()
    return SAMPLE_APP


def _client(info: TargetInfo) -> Hop3Client:
    return Hop3Client(
        base_url=info.api_url,
        token=create_test_token(secret_key=info.secret_key)
        if info.secret_key
        else create_test_token(),
    )


@pytest.fixture
def api(hop3_server: TargetInfo) -> Hop3Client:
    """The TUI's own client, talking to the container over the real JSON-RPC path."""
    return _client(hop3_server)
