# ... (imports and BuildpackBuilder class) ...
from __future__ import annotations

from hop3.config import UWSGI_ENABLED  # Add this import
from hop3.project.procfile import parse_procfile


class UWSGIDeployer:
    """The default deployment strategy, using uWSGI."""

    name = "uwsgi"

    def __init__(self, context: DeploymentContext):
        self.context = context
        self.app = context.app

    def accept(self, artifact: BuildArtifact) -> bool:
        return artifact.kind == "buildpack"

    def deploy(
        self, artifact: hookspecs.BuildArtifact, deltas: dict
    ) -> hookspecs.DeploymentInfo:
        # This is the old `spawn_app` function
        log(f"Deploying '{self.app.name}' with uWSGI...", level=2, fg="blue")
        spawn_app(self.app, deltas)

        # Mark the app as RUNNING in the database
        self.app.run_state = AppStateEnum.RUNNING

        # A more robust implementation would get this info from nginx/spawn logic
        return hookspecs.DeploymentInfo(
            protocol="unix_socket", address=f"/path/to/{self.app.name}.sock"
        )

    def start(self) -> None:
        """Starts the app by calling deploy with no scaling changes."""
        log(f"Starting '{self.app.name}' with uWSGI...", level=2, fg="blue")
        # For uWSGI, starting is the same as deploying the current state.
        self.deploy(None, {})  # `None` for artifact means "use existing"

    def stop(self) -> None:
        """Stops the app by removing its uWSGI .ini files from the enabled directory."""
        log(f"Stopping '{self.app.name}'...", level=2, fg="yellow")

        config_files = list(UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if not config_files:
            log(f"App '{self.app.name}' is already stopped or not deployed.", level=3)
            return

        for config_file in config_files:
            config_file.unlink()

        self.app.run_state = AppStateEnum.STOPPED
        log(f"App '{self.app.name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """For uWSGI, touching the .ini files is the most efficient way to restart."""
        log(f"Restarting '{self.app.name}'...", level=2, fg="blue")

        config_files = list(UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if not config_files:
            log(
                f"App '{self.app.name}' not running, cannot restart. Starting instead.",
                level=3,
            )
            self.start()
            return

        for config_file in config_files:
            # The uWSGI emperor will see the file modification and restart the vassal.
            config_file.touch()

        log(f"App '{self.app.name}' restart triggered.", level=2, fg="green")

    def destroy(self) -> None:
        """Destruction is a superset of stop."""
        self.stop()
        # Other runtime resource cleanup specific to uWSGI could go here,
        # but most is covered by the file-based approach.

    def scale(self, deltas: dict[str, int]) -> None:
        """Scaling is a specific type of deployment."""
        log(f"Scaling '{self.app.name}' with deltas: {deltas}", level=2, fg="blue")
        # For uWSGI, scaling is the same as re-deploying with new deltas
        self.deploy(None, deltas)

    def get_status(self) -> dict:
        """Gets process status from the SCALING file."""
        status = {
            "running": self.app.run_state == AppStateEnum.RUNNING,
            "processes": {},
        }

        scaling_file = self.app.virtualenv_path / "SCALING"
        if scaling_file.exists():
            worker_map = parse_procfile(scaling_file)
            status["processes"] = {k: int(v) for k, v in worker_map.items()}

        return status
