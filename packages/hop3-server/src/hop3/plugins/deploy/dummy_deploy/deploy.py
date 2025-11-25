# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import log


class DummyDeployer(Deployer):
    name = "dummy"

    def __init__(self, context: DeploymentContext, artifact: BuildArtifact):
        self.context = context
        self.artifact = artifact

    def accept(self) -> bool:
        return True

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        app_name = self.context.app_name

        log(f"Deploying '{app_name}' with uWSGI...", level=2, fg="blue")

        # Mark the app as RUNNING in the database
        # self.app.run_state = AppStateEnum.RUNNING

        # A more robust implementation would get this info from nginx/spawn logic
        return DeploymentInfo(
            protocol="unix_socket", address=f"/path/to/{app_name}.sock"
        )
