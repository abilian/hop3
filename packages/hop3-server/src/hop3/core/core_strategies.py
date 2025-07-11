from __future__ import annotations

from .protocols import (
    BuildArtifact,
    BuildStrategy,
    DeploymentContext,
    DeploymentInfo,
    DeploymentStrategy,
)


class BuildpackBuildStrategy(BuildStrategy):
    name = "buildpack"

    def __init__(self, context: DeploymentContext):
        self.context = context
        print(
            f"  [Strategy Init] BuildpackBuildStrategy initialized for '{context.app_name}'."
        )

    def accept(self) -> bool:
        print(
            "  [Strategy Check] BuildpackBuildStrategy checking 'requirements.txt'..."
        )
        return "requirements.txt" in self.context.app_config.get("files", [])

    def build(self) -> BuildArtifact:
        print("  [Strategy Exec] BuildpackBuildStrategy running `pip install`...")
        return BuildArtifact(
            kind="buildpack", location=f"/apps/{self.context.app_name}"
        )


class UWSGIDeploymentStrategy(DeploymentStrategy):
    name = "uwsgi"

    def __init__(self, context: DeploymentContext):
        self.context = context
        print(
            f"  [Strategy Init] UWSGIDeploymentStrategy initialized for '{context.app_name}'."
        )

    def accept(self, artifact: BuildArtifact) -> bool:
        print(
            "  [Strategy Check] UWSGIDeploymentStrategy checking if artifact is 'buildpack'..."
        )
        return artifact.kind == "buildpack"

    def deploy(self, artifact: BuildArtifact) -> DeploymentInfo:
        print(
            f"  [Strategy Exec] UWSGIDeploymentStrategy spawning uWSGI from '{artifact.location}'..."
        )
        return DeploymentInfo(
            protocol="unix_socket", address=f"/run/sockets/{self.context.app_name}.sock"
        )

    def stop(self): ...


class DockerBuildStrategy(BuildStrategy):
    name = "docker"

    def __init__(self, context: DeploymentContext):
        self.context = context
        print(
            f"  [Strategy Init] DockerBuildStrategy initialized for '{context.app_name}'."
        )

    def accept(self) -> bool:
        print("  [Strategy Check] DockerBuildStrategy checking for 'Dockerfile'...")
        return "Dockerfile" in self.context.app_config.get("files", [])

    def build(self) -> BuildArtifact:
        print(
            f"  [Strategy Exec] DockerBuildStrategy running `docker build -t hop3/{self.context.app_name}`..."
        )
        return BuildArtifact(
            kind="docker_image", location=f"hop3/{self.context.app_name}:latest"
        )


class DockerComposeDeploymentStrategy(DeploymentStrategy):
    name = "docker-compose"

    def __init__(self, context: DeploymentContext):
        self.context = context
        print(
            f"  [Strategy Init] DockerComposeDeploymentStrategy initialized for '{context.app_name}'."
        )

    def accept(self, artifact: BuildArtifact) -> bool:
        print(
            "  [Strategy Check] DockerComposeDeploymentStrategy checking if artifact is 'docker_image'..."
        )
        return artifact.kind == "docker_image"

    def deploy(self, artifact: BuildArtifact) -> DeploymentInfo:
        print(
            f"  [Strategy Exec] DockerComposeDeploymentStrategy running `docker-compose up` with image '{artifact.location}'..."
        )
        return DeploymentInfo(protocol="http", address="127.0.0.1", port=8080)

    def stop(self): ...
