# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Argument generation for CLI commands."""

from __future__ import annotations

import base64
import io
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import pathspec

if TYPE_CHECKING:
    from hop3_cli.types import JsonDict

__all__ = ["generate_archive", "get_extra_args", "pack_repository"]

# Archive size limits (in bytes)
# Soft limit: warn the user but proceed
# Hard limit: refuse to upload (can be overridden on server)
SOFT_SIZE_LIMIT = 100 * 1024 * 1024  # 100 MB
HARD_SIZE_LIMIT = 1024 * 1024 * 1024  # 1 GB

# Ignore files in priority order (first found is used)
IGNORE_FILES = [".hop3ignore", ".dockerignore", ".gitignore"]


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
            env_vars, remaining_args, streaming = _parse_deploy_args(args[1:])

            # Skip expensive archive generation if no app name provided
            # Let the server return a proper usage error instead
            if not remaining_args:
                return extra_args

            # Directory is the last non-flag argument (if any)
            directory = Path(remaining_args[-1]) if len(remaining_args) > 1 else Path()
            extra_args["repository"] = pack_repository(directory, verbosity=verbosity)

            # Include env vars if any were specified
            if env_vars:
                extra_args["env_vars"] = env_vars

            # Enable streaming by default for real-time log output
            extra_args["streaming"] = streaming

    return extra_args


def _parse_deploy_args(args: list[str]) -> tuple[dict[str, str], list[str], bool]:
    """Parse deploy command arguments, extracting --env and --no-stream flags.

    Args:
        args: Arguments after 'deploy' command (app_name, --env flags, directory)

    Returns:
        Tuple of (env_vars dict, remaining args, streaming enabled)

    Example:
        >>> _parse_deploy_args(['myapp', '--env', 'FOO=bar', '--env', 'BAZ=qux', '.'])
        ({'FOO': 'bar', 'BAZ': 'qux'}, ['myapp', '.'], True)
        >>> _parse_deploy_args(['myapp', '--no-stream'])
        ({}, ['myapp'], False)
    """
    env_vars: dict[str, str] = {}
    remaining: list[str] = []
    streaming = True  # Enabled by default
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
        elif arg == "--no-stream":
            # Disable real-time streaming (fallback to batch output)
            streaming = False
            i += 1
        elif arg == "--stream":
            # Explicitly enable streaming (default, but allow explicit)
            streaming = True
            i += 1
        else:
            remaining.append(arg)
            i += 1

    return env_vars, remaining, streaming


def pack_repository(directory: Path = Path(), verbosity: int = 1) -> str:
    """Pack a directory into a base64-encoded tar.gz archive.

    Args:
        directory: Directory to pack (defaults to current directory)
        verbosity: Verbosity level (0=quiet, 1=normal, 2+=verbose)

    Returns:
        Base64-encoded tar.gz archive
    """
    tar_gz = generate_archive(directory, verbosity=verbosity)
    return base64.b64encode(tar_gz).decode("ascii")


def generate_archive(source_dir: Path, verbosity: int = 1) -> bytes:
    """
    Creates an in-memory tar.gz archive of a source directory as a bytes object,
    excluding files and directories specified in ignore files.

    Ignore files are checked in priority order: .hop3ignore, .dockerignore, .gitignore

    Args:
        source_dir: The path to the directory to archive.
        verbosity: Verbosity level (0=quiet, 1=normal, 2+=verbose)

    Returns:
        The content of the .tar.gz archive as a bytes object.

    Raises:
        ValueError: If the source_dir is not a valid directory or has too many files.
        FileNotFoundError: If the source_dir does not exist.
    """
    source_dir = Path(source_dir).resolve()
    verbose = verbosity >= 2

    if not source_dir.exists():
        msg = (
            f"Directory not found: {source_dir}\n\n"
            f"Make sure you are in the directory containing your application code,\n"
            f"or specify the path as the last argument:\n"
            f"  hop3 deploy <app_name> /path/to/app"
        )
        raise FileNotFoundError(msg)
    if not source_dir.is_dir():
        msg = f"Path is not a directory: {source_dir}"
        raise ValueError(msg)

    # Check if directory looks like an application
    _check_directory_is_app(source_dir, verbose)

    if verbose:
        print(f"Creating archive from: {source_dir}", file=sys.stderr)

    # --- 1. Load ignore rules (.hop3ignore, .dockerignore, or .gitignore) ---
    spec, ignore_file = get_ignored_spec(source_dir)
    if verbose:
        if ignore_file:
            print(f"Using ignore patterns from: {ignore_file}", file=sys.stderr)
        else:
            print(
                "No ignore file found (.hop3ignore, .dockerignore, .gitignore)",
                file=sys.stderr,
            )

    # --- 2. Walk the directory and gather files to include ---
    if verbose:
        print("Scanning files...", file=sys.stderr)
    files_to_add = get_files_to_add(source_dir, spec)

    # --- 3. Log file count ---
    file_count = len(files_to_add)
    if verbose:
        print(f"Found {file_count} files to archive", file=sys.stderr)

    # --- 4. Create the tar.gz archive in memory ---
    if verbose:
        print("Creating archive...", file=sys.stderr)

    fileobj = io.BytesIO()

    # The 'w:gz' mode creates a gzip-compressed tar file.
    # We pass our BytesIO object as the file to write to.
    with tarfile.open(fileobj=fileobj, mode="w:gz") as tar:
        for file_path in files_to_add:
            relative_path = file_path.relative_to(source_dir)
            arcname = Path() / relative_path
            tar.add(file_path, arcname=str(arcname))

    archive_bytes = fileobj.getvalue()
    _check_archive_size(archive_bytes, files_to_add, source_dir, verbose)

    return archive_bytes


def _check_archive_size(
    archive_bytes: bytes,
    files: list[Path],
    source_dir: Path,
    verbose: bool,
) -> None:
    """Check archive size against soft and hard limits.

    Args:
        archive_bytes: The archive content
        files: List of files in the archive (for diagnostics)
        source_dir: Source directory (for computing relative paths)
        verbose: Whether to print verbose output
    """
    archive_size = len(archive_bytes)
    size_mb = archive_size / (1024 * 1024)

    if verbose:
        print(f"Archive created: {size_mb:.2f} MB", file=sys.stderr)

    if archive_size > HARD_SIZE_LIMIT:
        top_dirs = _get_top_directories_by_file_count(files, source_dir)
        dir_summary = "\n".join(f"  {d}: {c} files" for d, c in top_dirs[:5])
        hard_limit_mb = HARD_SIZE_LIMIT / (1024 * 1024)

        msg = (
            f"Archive too large: {size_mb:.1f} MB exceeds the {hard_limit_mb:.0f} MB limit.\n"
            f"\n"
            f"Directories with most files:\n"
            f"{dir_summary}\n"
            f"\n"
            f"Add directories to .hop3ignore to exclude them from deployment.\n"
            f"The server may also have configurable size limits."
        )
        raise ValueError(msg)

    if archive_size > SOFT_SIZE_LIMIT:
        soft_limit_mb = SOFT_SIZE_LIMIT / (1024 * 1024)
        print(
            f"Warning: Large archive ({size_mb:.1f} MB). "
            f"Uploads over {soft_limit_mb:.0f} MB may be slow.",
            file=sys.stderr,
        )


def get_ignored_spec(source_dir: Path) -> tuple[pathspec.PathSpec | None, str | None]:
    """Load ignore rules from a directory.

    Checks for ignore files in priority order: .hop3ignore, .dockerignore, .gitignore
    The first one found is used.

    Returns:
        Tuple of (PathSpec or None, filename used or None)
    """
    for ignore_file in IGNORE_FILES:
        ignore_path = source_dir / ignore_file
        if ignore_path.is_file():
            with ignore_path.open(encoding="utf-8") as f:
                spec = pathspec.PathSpec.from_lines("gitignore", f)
            return spec, ignore_file
    return None, None


def _get_top_directories_by_file_count(
    files: list[Path], source_dir: Path
) -> list[tuple[str, int]]:
    """Get the top-level directories sorted by file count.

    Args:
        files: List of file paths
        source_dir: The source directory (for computing relative paths)

    Returns:
        List of (directory_name, file_count) tuples, sorted by count descending
    """
    dir_counts: Counter[str] = Counter()
    for f in files:
        rel = f.relative_to(source_dir)
        # Get top-level directory, or "(root)" for files in root
        top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        dir_counts[top_dir] += 1

    return dir_counts.most_common()


def _check_directory_is_app(source_dir: Path, verbose: bool) -> None:
    """Check if the directory looks like an application and warn if not.

    Args:
        source_dir: The directory to check
        verbose: Whether to print verbose output
    """
    # Common app indicators
    app_indicators = [
        "Procfile",
        "hop3.toml",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "composer.json",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "index.html",
        "index.php",
    ]

    has_indicator = any((source_dir / f).exists() for f in app_indicators)

    if not has_indicator:
        # Check if directory has any files at all
        files = list(source_dir.iterdir())
        if not files:
            msg = (
                f"Directory is empty: {source_dir}\n\n"
                f"The deploy command expects a directory containing your application code.\n"
                f"Make sure you are in the correct directory."
            )
            raise ValueError(msg)

        # Directory has files but no recognizable app structure
        if verbose:
            print(
                f"Warning: No recognized application files found in {source_dir}\n"
                f"Expected one of: {', '.join(app_indicators[:5])}...\n"
                f"Proceeding anyway - the server will attempt to deploy.",
                file=sys.stderr,
            )


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
