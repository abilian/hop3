# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Base class for language toolchains."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from hop3.core.env import Env
from hop3.core.protocols import BuildArtifact, BuildContext
from hop3.lib import shell

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path


class LanguageToolchain(ABC):
    """A language-specific build toolchain.

    This abstract base class provides a framework for building applications in
    specific programming languages (Python, Node, Java, etc.). It defines
    properties and methods that are common to all toolchains, such as checking for file
    existence in a given path and executing shell commands. Subclasses must implement
    the abstract methods to provide specific behavior for accepting input and building
    the application.

    LanguageToolchains are used by LocalBuilder to build applications. Other builders
    (DockerBuilder, NixBuilder) do not use toolchains.

    Attributes
    ----------
    app_name : str
        The name of the application.
    app_path : Path
        The path to the application directory.
    context : BuildContext
        The build context.
    name : ClassVar[str]
        Class-level attribute representing the name of the toolchain.
    requirements : ClassVar[list[str]]
        Class-level attribute representing the list of requirements for the toolchain.
    """

    app_name: str
    app_path: Path
    context: BuildContext

    # Class attributes
    name: ClassVar[str]
    requirements: ClassVar[list[str]]

    def __init__(
        self,
        context_or_app_name: BuildContext | str,
        app_path: Path | None = None,
    ) -> None:
        """Initialize the toolchain with a build context or legacy parameters.

        Args:
        ----
            context_or_app_name: Either a BuildContext object (preferred) or app_name string (legacy)
            app_path: Legacy parameter - application path (only used with string app_name)
        """
        if isinstance(context_or_app_name, str):
            # Legacy style: string app_name + app_path
            # TODO: Remove in Phase 3 when LocalBuilder is implemented
            self.context = None  # type: ignore[assignment]
            self.app_name = context_or_app_name
            self.app_path = app_path  # type: ignore[assignment]
        else:
            # New style: BuildContext or DeploymentContext
            self.context = context_or_app_name
            self.app_name = context_or_app_name.app_name
            self.app_path = context_or_app_name.source_path.parent

    @abstractmethod
    def accept(self) -> bool:
        """Accepts the input specified by the subclass.

        Returns
        -------
            bool: True if this builder instance can accept the input, False otherwise.
        """

    def check_exists(self, file_or_files: str | list[str]) -> bool:
        """Check if the specified file, or one of the specified files, exist in
        the application path.

        Args:
        ----
            file_or_files (str|list[str]): The file or files to check for existence.

        Returns:
        -------
            bool: True if the file or files exist, False otherwise.
        """
        if isinstance(file_or_files, str):
            file_or_files = [file_or_files]
        # Check if any of the files exist in the source path
        return any((self.src_path / file).exists() for file in file_or_files)

    @abstractmethod
    def build(self) -> BuildArtifact:
        """Build app from sources (implemented by subclasses).

        Returns:
            BuildArtifact describing what was built
        """

    #
    # Properties
    #
    @property
    def src_path(self) -> Path:
        """Get the source path for the application."""
        if self.context is not None:
            return self.context.source_path
        # Legacy mode: app_path / src
        return self.app_path / "src"

    @property
    def virtual_env(self) -> Path:
        """Get the virtual environment path for the application."""
        return self.app_path / "venv"

    @property
    def env_file(self) -> Path:
        """Return the path to the environment file for the application."""
        return self.app_path / "ENV"

    def shell(
        self, command: str, cwd: str | Path = "", **kwargs
    ) -> subprocess.CompletedProcess:
        """Run a shell command with optional working directory and additional
        keyword arguments.

        Args:
        ----
            command (str): The shell command to be executed.
            cwd (str or Path, optional): The working directory where the command will be executed.
                Defaults to the application path if not provided.
            **kwargs: Additional keyword arguments to be passed to the shell function.
        """
        if not cwd:
            # Build in the source directory
            cwd = str(self.src_path)
        return shell(command, cwd=str(cwd), **kwargs)

    def get_env(self) -> Env:
        """Get the environment for this app instance as an Env object."""
        env = Env()
        # Parse settings from the environment file
        env.parse_settings(self.env_file)
        return env
