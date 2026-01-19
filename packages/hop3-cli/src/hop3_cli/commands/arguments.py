# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Argument generation for CLI commands."""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

import pathspec

from hop3_cli.types import JsonDict

__all__ = ["generate_archive", "get_extra_args", "pack_repository"]


def get_extra_args(args: list[str], verbosity: int = 1) -> JsonDict:
    """Generate a dictionary of extra arguments for RPC commands.

    Args:
        args: Command-line arguments
        verbosity: Verbosity level (0=quiet, 1=normal, 2=verbose, 3=debug)

    Returns:
        Dictionary with extra arguments. Verbosity is always included as it's
        used by the server to set the logging context for all commands.
    """
    # Always include verbosity - server extracts it and uses it as context
    extra_args: JsonDict = {"verbosity": verbosity}

    if not args:
        return extra_args

    command = args[0]

    match command:
        case "deploy":
            # Parse deploy-specific flags
            # args[0]="deploy", args[1]=app_name, remaining args may include --env and directory
            env_vars, remaining_args = _parse_deploy_args(args[1:])

            # Directory is the last non-flag argument (if any)
            directory = Path(remaining_args[-1]) if len(remaining_args) > 1 else Path()
            extra_args["repository"] = pack_repository(directory)

            # Include env vars if any were specified
            if env_vars:
                extra_args["env_vars"] = env_vars

    return extra_args


def _parse_deploy_args(args: list[str]) -> tuple[dict[str, str], list[str]]:
    """Parse deploy command arguments, extracting --env flags.

    Args:
        args: Arguments after 'deploy' command (app_name, --env flags, directory)

    Returns:
        Tuple of (env_vars dict, remaining args without --env flags)

    Example:
        >>> _parse_deploy_args(['myapp', '--env', 'FOO=bar', '--env', 'BAZ=qux', '.'])
        ({'FOO': 'bar', 'BAZ': 'qux'}, ['myapp', '.'])
    """
    env_vars: dict[str, str] = {}
    remaining: list[str] = []
    i = 0

    while i < len(args):
        arg = args[i]

        if arg in {"--env", "-e"}:
            # Next argument should be KEY=VALUE
            if i + 1 < len(args):
                env_spec = args[i + 1]
                if "=" in env_spec:
                    key, _, value = env_spec.partition("=")
                    env_vars[key] = value
                i += 2
            else:
                i += 1  # Skip malformed --env without value
        elif arg.startswith("--env="):
            # Handle --env=KEY=VALUE format
            env_spec = arg[6:]  # Remove --env=
            if "=" in env_spec:
                key, _, value = env_spec.partition("=")
                env_vars[key] = value
            i += 1
        else:
            remaining.append(arg)
            i += 1

    return env_vars, remaining


def pack_repository(directory: Path = Path()) -> str:
    """Pack a directory into a base64-encoded tar.gz archive.

    Args:
        directory: Directory to pack (defaults to current directory)

    Returns:
        Base64-encoded tar.gz archive
    """
    tar_gz = generate_archive(directory)
    return base64.b64encode(tar_gz).decode("ascii")


def generate_archive(source_dir: Path) -> bytes:
    """
    Creates an in-memory tar.gz archive of a source directory as a bytes object,
    excluding files and directories specified in a .gitignore file.

    Args:
        source_dir: The path to the directory to archive.

    Returns:
        The content of the .tar.gz archive as a bytes object.

    Raises:
        ValueError: If the source_dir is not a valid directory.
        FileNotFoundError: If the source_dir does not exist.
    """
    source_dir = Path(source_dir).resolve()

    if not source_dir.exists():
        msg = f"Source directory not found: {source_dir}"
        raise FileNotFoundError(msg)
    if not source_dir.is_dir():
        msg = f"Source path is not a directory: {source_dir}"
        raise ValueError(msg)

    # --- 1. Load .gitignore rules ---
    spec = get_ignored_spec(source_dir)

    # --- 2. Walk the directory and gather files to include ---
    files_to_add = get_files_to_add(source_dir, spec)

    # --- 3. Create the tar.gz archive in memory ---
    fileobj = io.BytesIO()

    # The 'w:gz' mode creates a gzip-compressed tar file.
    # We pass our BytesIO object as the file to write to.
    with tarfile.open(fileobj=fileobj, mode="w:gz") as tar:
        for file_path in files_to_add:
            relative_path = file_path.relative_to(source_dir)
            arcname = Path() / relative_path
            tar.add(file_path, arcname=str(arcname))

    return fileobj.getvalue()


def get_ignored_spec(source_dir: Path) -> pathspec.PathSpec | None:
    """Load .gitignore rules from a directory."""
    gitignore_path = source_dir / ".gitignore"
    spec: pathspec.PathSpec | None = None
    if gitignore_path.is_file():
        with gitignore_path.open(encoding="utf-8") as f:
            spec = pathspec.PathSpec.from_lines("gitignore", f)
    return spec


def get_files_to_add(source_dir: Path, spec: pathspec.PathSpec | None) -> list[Path]:
    """Get list of files to add to archive, excluding gitignored files."""
    files_to_add: list[Path] = []
    for file_path in source_dir.rglob("*"):
        relative_path = file_path.relative_to(source_dir)
        relative_str = str(relative_path)

        # Always exclude .git directory (not deployment material)
        if relative_str.startswith(".git") and (
            relative_str == ".git" or relative_str.startswith(".git/")
        ):
            continue

        # Let pathspec determine if the file should be ignored
        if spec and spec.match_file(relative_str):
            continue

        # We only add files to the tar, not directories
        if not file_path.is_file():
            continue

        files_to_add.append(file_path)
    return files_to_add
