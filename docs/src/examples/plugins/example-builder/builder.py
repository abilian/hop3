# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Example build strategy implementation.

This module demonstrates a minimal but complete build strategy.
It shows the core concepts without the complexity of a production builder.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.lib import Abort, log


class ExampleBuilder:
    """Example build strategy for Python applications.

    This builder demonstrates the BuildStrategy protocol implementation
    with a simple virtualenv-based build process.

    Attributes:
        name: Unique identifier for this builder
        context: Deployment context with app information

    Example:
        The builder is used automatically during deployment:

        ```bash
        hop deploy myapp
        ```

        The deploy command:
        1. Calls accept() to check if this builder should be used
        2. If accepted, calls build() to create the artifact
        3. Uses the returned BuildArtifact for deployment
    """

    name = "example-python"

    def __init__(self, context: DeploymentContext):
        """Initialize builder with deployment context.

        Args:
            context: Deployment context containing app_name, source_path, etc.
        """
        self.context = context

    def accept(self) -> bool:
        """Check if this builder can build the application.

        Returns:
            True if requirements.txt exists, False otherwise

        Note:
            This method should be fast. Don't perform expensive operations here.
        """
        src_path = self.context.source_path
        requirements_file = src_path / "requirements.txt"

        # Simple detection: check for requirements.txt
        return requirements_file.exists()

    def build(self) -> BuildArtifact:
        """Build the Python application.

        This creates a virtualenv and installs dependencies from requirements.txt.

        Returns:
            BuildArtifact with information about the created virtualenv

        Raises:
            Abort: If build fails for any reason
        """
        app_name = self.context.app_name
        src_path = self.context.source_path

        log(f"Building Python application '{app_name}'...", level=1, fg="blue")

        # Determine virtualenv location
        # In a real implementation, this would come from HopConfig
        venv_path = Path(f"/tmp/example-venv/{app_name}")

        try:
            # Create virtualenv
            self._create_virtualenv(venv_path)

            # Install dependencies
            self._install_dependencies(venv_path, src_path)

            # Get Python version for metadata
            python_version = self._get_python_version(venv_path)

            log(f"Build successful for '{app_name}'", level=1, fg="green")

            # Return build artifact information
            return BuildArtifact(
                kind="virtualenv",
                location=str(venv_path),
                metadata={
                    "python_version": python_version,
                    "builder": self.name,
                },
            )

        except subprocess.CalledProcessError as e:
            msg = f"Build failed for '{app_name}': {e}"
            raise Abort(msg) from e
        except Exception as e:
            msg = f"Unexpected error building '{app_name}': {e}"
            raise Abort(msg) from e

    def _create_virtualenv(self, venv_path: Path) -> None:
        """Create a Python virtualenv.

        Args:
            venv_path: Path where virtualenv should be created
        """
        log(f"Creating virtualenv at {venv_path}...", level=2, fg="blue")

        # Remove existing virtualenv if it exists
        if venv_path.exists():
            import shutil

            shutil.rmtree(venv_path)

        # Create parent directory
        venv_path.parent.mkdir(parents=True, exist_ok=True)

        # Create virtualenv using venv module
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )

        log("Virtualenv created", level=2, fg="green")

    def _install_dependencies(self, venv_path: Path, src_path: Path) -> None:
        """Install dependencies from requirements.txt.

        Args:
            venv_path: Path to virtualenv
            src_path: Path to application source code
        """
        log("Installing dependencies...", level=2, fg="blue")

        pip_path = venv_path / "bin" / "pip"
        requirements_file = src_path / "requirements.txt"

        # Upgrade pip first (optional but recommended)
        subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
        )

        # Install dependencies
        subprocess.run(
            [str(pip_path), "install", "-r", str(requirements_file)],
            check=True,
            cwd=src_path,
        )

        log("Dependencies installed", level=2, fg="green")

    def _get_python_version(self, venv_path: Path) -> str:
        """Get Python version from virtualenv.

        Args:
            venv_path: Path to virtualenv

        Returns:
            Python version string (e.g., "3.11.2")
        """
        python_path = venv_path / "bin" / "python"

        result = subprocess.run(
            [str(python_path), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )

        # Output is like "Python 3.11.2"
        version = result.stdout.strip().split()[1]
        return version
