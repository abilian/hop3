# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`docker cp SRC CONTAINER:DEST` copies SRC *into* an existing DEST directory.

The update path uploads to the same /tmp/hop3-server every time, so the second
upload nested the new tree inside the old one and `pip install /tmp/hop3-server`
reinstalled the old code with a green message (2026-09-09, upgrade chain).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig


def test_upload_dir_removes_the_destination_before_copying():
    backend = DockerDeployBackend(DeployConfig(use_docker=True))
    issued: list[str] = []

    def record(command: str, **_kwargs):
        issued.append(command)
        return SimpleNamespace(success=True, stdout="", stderr="", returncode=0)

    copied: list[list[str]] = []

    def fake_cp(argv, **_kwargs):
        copied.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    with (
        patch.object(backend, "run", side_effect=record),
        patch(
            "hop3_installer.deployer.backends.docker.subprocess.run",
            side_effect=fake_cp,
        ),
    ):
        assert backend.upload_dir(Path("/src/hop3-server"), "/tmp/hop3-server") is True

    assert issued[0] == "rm -rf /tmp/hop3-server"
    assert copied
    assert copied[0][:2] == ["docker", "cp"]
    assert copied[0][-1].endswith(":/tmp/hop3-server")
