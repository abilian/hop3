# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Adapt a raw docker-py container to the DeploymentTarget contract.

Some pytest fixtures (e.g. the proxy tests) yield a raw docker-py container
rather than a ``DeploymentTarget``. ``ContainerTarget`` wraps such a container so
the diagnostic-bundle collector — which only needs ``exec_run`` — can run over it
unchanged. The container lifecycle stays owned by the fixture, so ``start``/
``stop`` are no-ops.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any

from hop3_testing.targets.base import DeploymentTarget, TargetInfo

if TYPE_CHECKING:
    from collections.abc import Sequence


class ContainerTarget(DeploymentTarget):
    """
    Minimal DeploymentTarget over an existing docker-py container.

    Only ``exec_run`` is meaningful. Commands run via ``bash -c`` as ``root`` so
    the bundle's shell pipelines (``;``, ``||``, ``$(...)``) and root-only reads
    (nginx error.log, journalctl) work — matching ``DockerCommandRunner``.
    """

    def __init__(self, container: Any, *, user: str = "root") -> None:
        self._container = container
        self._user = user

    def start(self) -> TargetInfo:  # lifecycle owned by the fixture
        return TargetInfo(ssh_host="container", ssh_port=0)

    def stop(self) -> None:  # lifecycle owned by the fixture
        return

    def exec_run(self, cmd: str | Sequence[str]) -> tuple[int, str, str]:
        """Run ``cmd`` in the container, returning ``(exit_code, stdout, stderr)``."""
        if not isinstance(cmd, str):
            cmd = shlex.join(cmd)
        result = self._container.exec_run(
            ["bash", "-c", cmd], demux=True, user=self._user
        )
        out, err = result.output
        stdout = out.decode() if out else ""
        stderr = err.decode() if err else ""
        return result.exit_code, stdout, stderr
