# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""uWSGI accepts by builder, not by a list of language artifact kinds."""

from __future__ import annotations

import pytest

from hop3.core.artifacts import BuildArtifact
from hop3.core.protocols import DeploymentContext
from hop3.plugins.deploy.uwsgi.deployer import UWSGIDeployer


@pytest.mark.parametrize(
    ("builder", "kind", "accepted"),
    [
        ("local", "python", True),
        ("local", "kotlin", True),  # a toolchain core has never heard of
        ("nix", "nix", True),
        ("nix", "static", False),  # a Nix site: the proxy serves it
        ("local", "static", False),
        ("docker", "docker-image", False),
    ],
)
def test_accept(tmp_path, builder: str, kind: str, accepted: bool) -> None:
    ctx = DeploymentContext(app_name="myapp", source_path=tmp_path, app_config={})
    artifact = BuildArtifact(kind=kind, builder=builder)
    assert UWSGIDeployer(ctx, artifact).accept() is accepted
