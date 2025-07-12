from __future__ import annotations

from typing import cast

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildArtifact, BuildStrategy, DeploymentContext


class DummyBuildStrategy(BuildStrategy):
    name = "dummy"

    def __init__(self, context: DeploymentContext):
        self.context = context

    def accept(self) -> bool:
        return True

    def build(self) -> BuildArtifact:
        """Runs `docker build` and returns a docker_image artifact."""
        app_name = self.context.app_name

        # # A simple tagging scheme: hop3/<app-name>:latest
        # image_tag = f"hop3/{app_name}:latest"
        # src_path = self.context.app_config.src_dir_path
        #
        # log(f"Starting Docker build for image: {image_tag}", level=2, fg="blue")
        #
        # try:
        #     # Using subprocess.run for simplicity. A real implementation might
        #     # stream the output line by line using Popen.
        #     cmd = ["docker", "build", "-t", image_tag, "."]
        #     result = subprocess.run(
        #         cmd, cwd=src_path, check=True, capture_output=True, text=True
        #     )
        #     log(result.stdout, level=3)
        # except FileNotFoundError:
        #     raise Abort(
        #         "Docker command not found. Is Docker installed and in your PATH?"
        #     )
        # except subprocess.CalledProcessError as e:
        #     log(f"Docker build failed with exit code {e.returncode}:", fg="red")
        #     log(e.stderr, fg="red")
        #     raise Abort("Docker build failed.")
        #
        # log(f"Docker image '{image_tag}' built successfully.", fg="green")
        #
        # # We could inspect the image to find exposed ports, but for now
        # # we'll rely on the docker-compose file to map them.
        return BuildArtifact(kind="dummy-artifact", location="/tmp")


class DummyPlugin:
    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        return cast(list[type[BuildStrategy]], [DummyBuildStrategy])

    # @hop3_hook_impl
    # def get_deployment_strategies(self) -> List[Type[DeploymentStrategy]]:
    #     return cast(List[Type[DeploymentStrategy]], [DockerComposeDeploymentStrategy])
