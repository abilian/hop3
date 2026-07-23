# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Base class for language toolchains."""

from __future__ import annotations

import os
import pwd
import subprocess
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, assert_never

from hop3.core.artifacts import BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.lib import shell
from hop3.project.procfile import parse_procfile

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hop3.core.protocols import BuildContext


class LanguageToolchain(ABC):
    """
    A language-specific build toolchain.

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
        """
        Initialize the toolchain with a build context or legacy parameters.

        Args:
        ----
            context_or_app_name: Either a BuildContext object (preferred) or app_name string (legacy)
            app_path: Legacy parameter - application path (only used with string app_name)
        """
        match context_or_app_name:
            case str():
                # Legacy style: string app_name + app_path. Still exercised by
                # the toolchain unit tests (test_builders / test_builder_init /
                # test_virtualenv_repair); removing it means migrating those to
                # the BuildContext form first.
                self.context = None  # type: ignore[assignment]
                self.app_name = context_or_app_name
                self.app_path = app_path  # type: ignore[assignment]
            case _:
                # New style: BuildContext or DeploymentContext
                self.context = context_or_app_name
                self.app_name = context_or_app_name.app_name
                self.app_path = context_or_app_name.source_path.parent

    @abstractmethod
    def accept(self) -> bool:
        """
        Accepts the input specified by the subclass.

        Returns
        -------
            bool: True if this builder instance can accept the input, False otherwise.
        """

    def check_exists(self, file_or_files: str | list[str]) -> bool:
        """
        Check if the specified file, or one of the specified files, exist in
        the application path.

        Args:
        ----
            file_or_files (str|list[str]): The file or files to check for existence.

        Returns:
        -------
            bool: True if the file or files exist, False otherwise.
        """
        match file_or_files:
            case str():
                files = [file_or_files]
            case list():
                files = file_or_files
            case _ as unreachable:
                assert_never(unreachable)
        # Check if any of the files exist in the source path
        return any((self.src_path / file).exists() for file in files)

    def _get_custom_build_command(self) -> str | None:
        """
        Get custom build command from hop3.toml if specified.

        Returns:
            Build command string, or None if not specified.
            If multiple commands are specified as a list, they are joined with ' && '.
        """
        if self.context is None:
            return None

        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        build_section = hop3_config.get("build", {})
        build_cmd = build_section.get("build")

        match build_cmd:
            case list() if build_cmd:
                return " && ".join(build_cmd)
            case str() if build_cmd:
                return build_cmd
            case _:
                return None

    @abstractmethod
    def build(self) -> BuildArtifact:
        """
        Build app from sources (implemented by subclasses).

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
        self,
        command: str,
        cwd: str | Path = "",
        *,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a shell command in the app's source directory.

        Args:
        ----
            command (str): The shell command to be executed.
            cwd (str or Path, optional): The working directory where the command will be executed.
                Defaults to the source path if not provided.
            env: Environment for the command; merged over os.environ when given.
            check: Raise CalledProcessError on a non-zero exit (default: True).

        The env is automatically merged with os.environ to ensure all system
        variables are available. This is important because subprocess.run with
        a custom env parameter replaces the entire environment.
        """
        if not cwd:
            # Build in the source directory
            cwd = str(self.src_path)

        merged_env: dict[str, str] | None = None
        if env is not None:
            # subprocess.run replaces the entire environment when env is passed,
            # so start from os.environ and overlay the caller's values, keeping
            # system vars like HOME, USER, LANG available.
            merged_env = dict(os.environ)
            merged_env.update(env)

            # Ensure HOME is set (required by npm, composer, pnpm, etc.)
            if not merged_env.get("HOME"):
                merged_env["HOME"] = self._get_home_dir()

        return shell(command, cwd=str(cwd), env=merged_env, check=check)

    def _get_home_dir(self) -> str:
        """
        Get the home directory, handling systemd/service environments.

        In systemd services or restricted environments, HOME may not be set,
        so we use pwd module or fall back to hop3 user's home.
        """
        # Try environment first
        home = os.environ.get("HOME")
        if home:
            return home

        # Try passwd database
        try:
            return pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            pass

        # Fallback to hop3's default home
        return "/home/hop3"

    def get_env(self) -> Env:
        """Get the environment for this app instance as an Env object."""
        env = Env()
        # Parse settings from the environment file
        env.parse_settings(self.env_file)
        return env

    #
    # BuildArtifact helpers
    #
    def _get_workers(self) -> dict[str, str]:
        """
        Parse Procfile and return worker commands.

        Checks for Procfile in:
        1. src_path/hop3/Procfile (alternate config path)
        2. src_path/Procfile (standard location)

        This matches the behavior of AppConfig.get_file().

        Returns:
            Dict mapping worker names to commands, e.g. {"web": "gunicorn app:app"}
        """
        # Check hop3/ subdirectory first (alternate config path)
        procfile = self.src_path / "hop3" / "Procfile"
        if procfile.exists():
            return dict(parse_procfile(procfile))

        # Check standard location
        procfile = self.src_path / "Procfile"
        if procfile.exists():
            return dict(parse_procfile(procfile))

        return {}

    def _get_build_id(self) -> str:
        """
        Get build ID from git SHA or generate UUID.

        Returns:
            A short identifier for this build (12 chars)
        """
        git_dir = self.src_path / ".git"
        if git_dir.exists():
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.src_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    return result.stdout.strip()[:12]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return str(uuid.uuid4())[:12]

    def _get_build_timestamp(self) -> str:
        """Get current timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()

    def _make_runtime_config(
        self,
        env_vars: dict[str, str] | None = None,
        path_prepend: list[str] | None = None,
        workers: dict[str, str] | None = None,
    ) -> RuntimeConfig:
        """
        Create a RuntimeConfig with common defaults.

        Args:
            env_vars: Additional environment variables to set
            path_prepend: Paths to prepend to PATH
            workers: Explicit worker map. Defaults to the Procfile-derived
                workers; a toolchain that knows its own process model (e.g. the
                static toolchain) passes it directly so a Procfile is never
                required.

        Returns:
            RuntimeConfig with the given (or Procfile-derived) workers and settings
        """
        return RuntimeConfig(
            env_vars=env_vars or {},
            path_prepend=path_prepend or [],
            working_dir=str(self.src_path),
            workers=self._get_workers() if workers is None else workers,
        )

    def _make_build_artifact(
        self,
        kind: str,
        runtime: RuntimeConfig | None = None,
        metadata: dict | None = None,
    ) -> BuildArtifact:
        """
        Create a complete BuildArtifact.

        Args:
            kind: Artifact kind (e.g., "python", "node", "ruby")
            runtime: RuntimeConfig (created with defaults if not provided)
            metadata: Additional metadata

        Returns:
            Complete BuildArtifact ready for serialization
        """
        return BuildArtifact(
            kind=kind,
            builder="local",
            app_name=self.app_name,
            built_at=self._get_build_timestamp(),
            build_id=self._get_build_id(),
            location=str(self.src_path),
            runtime=runtime or self._make_runtime_config(),
            metadata=metadata or {},
        )
